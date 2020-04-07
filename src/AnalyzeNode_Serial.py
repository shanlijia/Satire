

import sys
import time
import globals
from gtokens import *
import symengine as seng
import ops_def as ops

from collections import defaultdict
import utils
import helper

import logging

logger = logging.getLogger(__name__)


class AnalyzeNode_Serial(object):

	def initialize(self):
		self.workList = []
		self.next_workList = []
		self.parentTracker = defaultdict(int)
		self.completed = defaultdict(set)
		self.Accumulator = defaultdict(int)
		self.results = {}
		self.bwdDeriv = defaultdict(dict)


	def __init__(self, probeNodeList, argList):
		self.initialize()
		self.probeList = probeNodeList
		self.argList   = argList
		self.parent_dict = helper.build_partial_ast(probeNodeList)
		self.__init_workStack__()
		self.__setup_outputs__()

	def __setup_outputs__(self):
		for node in self.probeList:
			self.bwdDeriv[node] = {node : 1}
			self.parentTracker[node] = len(self.parent_dict[node])

	def __init_workStack__(self):
		max_depth = max(list(map(lambda x: x.depth, self.probeList)))
		#print(max_depth)
		it1, it2 = utils.partition(self.probeList, lambda x:x.depth==max_depth)
		self.next_workList = list(it1)
		self.workList = list(it2)
	
	def converge_parents(self, node):
		#print(id(node), node.depth, self.parentTracker[node], len(node.parents) , len(self.parent_dict[node]))
		#print(node.f_expression, "\n")
		return True if self.parentTracker[node] == len(self.parent_dict[node]) else False
	
	def visit_node_deriv(self, node):
		outList = self.bwdDeriv[node].keys()
		opList = [child.f_expression for child in node.children]
		if(len(node.children) > 0):
			DerivFunc = ops._DFOPS[node.token.type]
			for i, child_node in enumerate(node.children):
				for outVar in outList:
					self.bwdDeriv[child_node][outVar] = self.bwdDeriv[child_node].get(outVar, 0) +\
					                       self.bwdDeriv[node][outVar] * \
										   (0 if utils.isConst(child_node) else \
										   DerivFunc[i](opList))
					self.next_workList.append(child_node)
				self.parentTracker[child_node] += 1
		self.completed[node.depth].add(node)


	def traverse_ast(self):
		next_workList = []
		curr_depth = 0
		next_depth = -1
		while(len(self.workList) > 0):
			node = self.workList.pop(0)
			curr_depth = node.depth
			next_depth = curr_depth - 1
			if (utils.isConst(node) or self.completed[node.depth].__contains__(node) ):
			    pass
			elif (self.converge_parents(node)):
			    self.visit_node_deriv(node)
			else:
			    self.workList.append(node)
			
			if(len(self.workList)==0 and next_depth!=-1 and len(self.next_workList)!=0):
			    nextIter, currIter = utils.partition(self.next_workList, \
			                                           lambda x:x.depth==next_depth)
			    self.workList = list(set(currIter))
			    self.next_workList = list(set(nextIter))


	def propagate_symbolic(self, node):
		for outVar in self.bwdDeriv[node].keys():
			expr_solve = (((\
			                (self.bwdDeriv[node][outVar]))*\
							(node.get_noise(node))*node.get_rounding())\
							).__abs__()

			if seng.count_ops(self.Accumulator[outVar]) > 4000:
				intv = max(utils.generate_signature(self.Accumulator[outVar]))
				self.Accumulator[outVar] = expr_solve
				expr_solve = intv
			elif seng.count_ops( expr_solve ) > 1000:
				expr_solve = max(utils.generate_signature(expr_solve))
			self.Accumulator[outVar] += expr_solve


	def visit_node_ferror(self, node):
		
		for child in node.children:
			if not self.completed[child.depth].__contains__(child):
				self.visit_node_ferror(child)

		self.propagate_symbolic(node)
		self.completed[node.depth].add(node)


	def first_order_error(self):

		for node in self.probeList:
			if not self.completed[node.depth].__contains__(node):
				self.visit_node_ferror(node)

		for node in self.Accumulator.keys():
			errIntv = utils.generate_signature(self.Accumulator[node])
			err = max([abs(i) for i in errIntv])
			fintv = utils.generate_signature(node.f_expression)
			self.results[node] = { "ERR" : err, \
								  "SERR" : 0.0, \
								  "INTV" : fintv \
								 }

		return self.results
			


	def start(self):

		print("Begin Derivatives\n", time.time())
		self.traverse_ast()
		print("Finished Derivatives\n", time.time())
		self.completed.clear()
		return self.first_order_error()

	