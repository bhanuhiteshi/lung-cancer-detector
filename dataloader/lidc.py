from __future__ import print_function
import numpy as np
import pandas as pd
import pickle as p
import os
import math
from dataloader.base_dataloader import BaseDataLoader

from utils import dicom_processor as dp, lidc_xml_parser

class LIDCData(BaseDataLoader):
	def __init__(self, config):
		super(LIDCData, self).__init__(config)
		self._load()

	def data_iter(self):
		#a generator to go through the dataset in a loop
		current_pointer = 0

		batch_X = batch_Y = []
		count = 0
		
		while current_pointer < self._current_set_size:
			(img, s, o, origShape) = p.load(open(os.path.join(self._target_directory, 
				self._X[current_pointer] + ".pick"), "rb"))
			
			for sliceIdx in range(img.shape[0]):
				batch_X.append(img[sliceIdx])
				# TODO Create the correct mask here
				#depending on the nodule info
				batch_Y.append(np.zeros_like(img[sliceIdx]))
				count += 1

				if count % self._batch_size == 0:
					yield np.array(batch_X), np.array(batch_Y)
					count = 0
					batch_X = batch_Y = []

			current_pointer += 1

		if len(batch_X) > 0:
			yield np.array(batch_X), np.array(batch_Y)

	def train(self, do_shuffle=True):
		if do_shuffle:
			self.shuffle()

		train_size = int(math.ceil((1.0 - self._val) * len(self._train_set)))
		self._current_set_x = self._X[:train_size]
		self._current_set_size = train_size

	def validate(self):
		if do_shuffle:
			self.shuffle()

		train_size = int(math.ceil((1.0 - self._val) * len(self._train_set)))
		self._current_set_x = self._X[train_size:]
		self._current_set_size = len(self._current_set_x)

	def test(self):
		#No testing, only validation
		self.validate()

	def shuffle(self):
		#Shuffle the dataset
		self._X = [self._X[i] for i in np.random.permutation(len(self._X))]

	def _create_datasets(self):
		#XML dataset is already created.
		#We just need to build a the list
		#of patients we have
		for name in os.listdir(self._target_directory):
			root, ext = os.apth.splitext(name)
			if root == "nodule_info" or root == "norm_para":
				continue
			else:
				self._X.append(name)

	def _studies_directory_iter(self):
		for i in os.listdir(self._studies):
			di = os.path.join(self._studies, i)
			for j in os.listdir(di):
				dj = os.path.join(di, j)
				for k in os.listdir(dj):
					dk = os.path.join(dj, k)
					name = k[k.rfind('.')+1:]
					yield dk, name

	def _pre_process_images(self):
		print("Pre-processing images...")
		
		total_scans = sum(1 for i in self._studies_directory_iter())

		count = 1
		for path, name in self._studies_directory_iter():
			print("{}/{}Processing ".format(count, total_scans), name)
			count += 1

			for s in os.listdir(path):
				root, ext = os.path.splitext(s)
				if ext != '.dcm':
					os.remove(os.path.join(path, s))
			if self._original_size:
				resize = None
			else:
				resize = self._size

			try:
				scan = dp.load_lidc_scan(path, resize)

				if not scan:
					self._ignored_scans.append(name)
			except:
				#If this error occurs, manual intervention 
				#is required right now
				print("Error with ", path)
				dp.load_lidc_scan(path, resize, print_details=True)
				if name in self._nodule_info:
					print("Nodules exist for this series")
				continue
			
			p.dump(scan, 
				open(os.path.join(self._target_directory, name + ".pick"), "wb"), 
				protocol=2)

		p.dump(self._ignored_scans, 
			open(os.path.join(self._target_directory, "ignored_scans.pick"), "wb"),
			protocol=2)
		print("Image pre-processing complete!")

	def _pre_process_XMLs(self):
		print("Pre-processing XMLs...")
		
		nodule_info_list = lidc_xml_parser.load_xmls(self._xmls)
		#Create a more sensible list for iteration
		#over the dataset of nodules
		self._nodule_info = {}
		for nodule_info in nodule_info_list:
			series = nodule_info['header']['uid']
			if series not in self._nodule_info:
				self._nodule_info[series] = []

			for nodule in nodule_info['readings']:
				#We'll ignore the Non-Nodules right now
				if nodule.is_nodule():
					for roi in nodule.get_roi():
						z = roi.z
						iid = roi.image_uid
						vertices = [(edge.x, edge.y) for edge in roi.get_edges()]
						self._nodule_info[series].append((iid, z, vertices))

		p.dump(self._nodule_info, 
			open(os.path.join(self._target_directory, "nodule_info.pick"), "wb"),
			protocol=2)
		print("XMLs pre-processing completes...")

	def _check_valid_dicom(self, path):
		try:
			slices = dp.load_lidc_scan(path)
			if not slices:
				return False
		except:
			#Some unknown error occured in loading
			#the dicom
			#Manual intervention required
			print("Some problem with path: ", path)
			return False

		return True

	def _pre_process_exists(self):
		if not(os.path.exists(self._target_directory) 
			and os.path.isdir(self._target_directory)):
			return False

		#Check if all patients exists
		for path, name in self._studies_directory_iter():
			if not os.path.exists(os.path.join(self._target_directory, name + ".pick")):
				if self._check_valid_dicom(path):
					return False

		if not os.path.exists(os.path.join(self._target_directory, "nodule_info.pick")):
			return False


		print("Found pre-processed datasets")
		return True

	def _load_preprocessed_data(self):
		self._nodule_info = p.load(open(os.path.join(self._target_directory, "nodule_info.pick"), "rb"))

	def _pre_process(self):
		if self._pre_process_exists():
			print("Pre-processed dataset exists!")
			self._load_preprocessed_data()
			return
		print("No pre-processed dataset found...")

		if not(os.path.exists(self._target_directory)):
			os.makedirs(self._target_directory)
		
		self._pre_process_XMLs()
		self._pre_process_images()

		print("Pre-processing Done!")

	def _get_directory(self):
		return "lidc"

	def _set_directories(self):
		self._directory = "data/" + self._get_directory()
		if self._original_size:
			self._target_directory = "data/preprocessed/" + self._get_directory() + "/original"
		else:
			self._target_directory = "data/preprocessed/" + self._get_directory() + "/" \
					+ str(self._size[0]) + "_" + str(self._size[1]) + "_" + str(self._size[2])

		self._studies = os.path.join(self._directory, "studies")
		self._xmls = os.path.join(self._directory, "XMLs")

	def _load(self):
		self._size = self._config.size
		self._original_size = self._config.original

		self._batch_size = self._config.batch
		self._no_val = self._config.no_validation
		if self._no_val:
			self._val = 0
		else:
			self._val = self._config.validation_ratio

		self._X = []

		self._current_set_x = None
		self._current_set_size = 0

		self._ignored_scans = []

		self._set_directories()
		self._pre_process()
		self._create_datasets()

		self.train()

def get_data_loader(config):
	return LIDCData(config)
