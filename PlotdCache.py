# -*- coding: utf-8 -*-
#
# Copyright 2015 Institut für Experimentelle Kernphysik - Karlsruher Institut für Technologie
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import json
import re
from sqlalchemy import Column, TEXT
import urllib

import hf

class PlotdCache(hf.module.ModuleBase):
	
	config_keys = {
		"source_url" : ("Not used but filled to avoid warnings.", ""),
		"pool" : ("The pool the information is plotted for.", "")
#		"file_loc" : ("Location of the json file used to generate the plot.", "")
	}
	
	table_columns = [
		Column("filename_plot", TEXT)
	],["filename_plot"]
	
	def prepareAcquisition(self):
		
		# Setting the source url.
		self.source_url = self.config["source_url"]
	
	def extractData(self):
		data = {}
		self.pool_data = {}
		self.sum_prot = {}
		self.sum_pool = {}
		self.difference = []
		response = urllib.urlopen(self.source_url)
		for entry in sorted(json.loads(response.read()), key = lambda x: x.get('moverStart')):
			for element in self.config['pool'].split(','):
				if element in entry.get('pool'):
					pool = entry.get('pool')
					if 'receiving' in entry.get('sessionStatus').lower():
						direction = 'in'
					else:
						direction = 'out'
					prot = entry.get('protocol')
					throughput = entry.get('transferRate')
					if pool == '<unknown>':
						continue
					# Calculate the difference between waiting and start time.
					self.difference.append(entry.get('moverStart') - entry.get('waitingSince'))
					if pool and direction and prot and throughput:
						self.pool_data.setdefault(pool, {}).setdefault(direction, {}).setdefault(prot, []).append(throughput)
						self.sum_prot[direction][prot] = self.sum_prot.setdefault(direction, {}).get(prot, 0) + throughput
						self.sum_pool[direction][pool] = self.sum_pool.setdefault(direction, {}).get(pool, 0) + throughput

		self.pool_list = sorted(self.pool_data, key = lambda p: (p.split('_')[1][1:], p))
		self.pool_list.reverse()
		# Plot creation for user statistics
                data["filename_plot"] = self.plot()
		return data
			
	def plot(self):
		import numpy
		import matplotlib
		matplotlib.use("agg")
		import matplotlib.pyplot
		color = {
                        'dcap-3|0': '#ff0000',
                        'dcap-3|1': '#bb0000',

                        'GFtp-1|0': '#0000ff',
                        'GFtp-1|1': '#0000bb',

                        'GFtp-2|0': '#6666ff',
                        'GFtp-2|1': '#6666bb',

                        'Xrootd-2.7|0': '#00ffff',
                        'Xrootd-2.7|1': '#00bbbb',

                        'NFSV4.1-0|0': '#7CFC00',
                        'NFSV4.1-0|1': '#ADFF2F',
                        }	
		# Create Plot.
		plot_height = len(self.pool_list) * 10./12
		fig = matplotlib.pyplot.figure(figsize = (7,plot_height))
		fig.subplots_adjust(left=0.03, right=0.97, top = 0.99, bottom = 0.075, wspace = 0.95)

		ax = {}
		ax['in'] = fig.add_subplot(121)
		ax['out'] = fig.add_subplot(122)
		ax['in'].yaxis.set_ticks([])
		ax['out'].yaxis.set_ticks(range(len(self.pool_list)))
		ax['out'].yaxis.set_ticklabels(self.pool_list)
		ax['in'].set_xlabel('Incoming [MB/s]')
		ax['out'].set_xlabel('Outgoing [MB/s]')
		ax['in'].set_xlim((max(self.sum_pool.get('in', {None: 0}).values())/1.e3 + 10, 0))
		ax['out'].set_xlim((0, max(self.sum_pool.get('out', {None: 0}).values())/1.e3 + 10))

		for direction in ['in', 'out']:
			for pidx, pool in enumerate(self.pool_list):
				position = 0
				pool_info = self.pool_data.get(pool, {}).get(direction, {})
				for prot in sorted(pool_info):
					for sidx, entry in enumerate(pool_info[prot]):
						entry = entry / 1000.
						ax[direction].barh(pidx - 0.5, entry, 1, position,
							color = color['%s|%d' % (prot, sidx % 2)], linewidth = 0)
						position += entry

			if direction == 'in':
				patches = []
				labels = []
				for prot in sorted(set(map(lambda s: s.split('|')[0], color))):
					item = ''
					if self.sum_prot.get('in', {}).get(prot, 0) or self.sum_prot.get('out', {}).get(prot, 0):
						item = prot
					if self.sum_prot.get('out', {}).get(prot, 0):
						item += '\nread: %.1f MB/s' % (self.sum_prot['out'][prot] / 1e3)
					if self.sum_prot.get('in', {}).get(prot, 0):
						item += '\nwrite: %.1f MB/s' % (self.sum_prot['in'][prot] / 1e3)
					if item:
						patches.append(matplotlib.patches.Rectangle((0, 0), 1, 1, color = color['%s|0' % prot]))
						labels.append(item)
				ax[direction].set_xticklabels(map(lambda x: '%d' % x, ax[direction].xaxis.get_ticklocs()), rotation=45)
			else:
				ax[direction].set_xticklabels(map(lambda x: '%d' % x, ax[direction].xaxis.get_ticklocs()), rotation=-45)
			ax[direction].set_ylim((-0.5, len(self.pool_list)-0.5))
			ax[direction].grid(axis = 'x')
		
		ax['in'].legend(patches, labels, labelspacing = 1, prop = matplotlib.font_manager.FontProperties(size = 9), loc = 'best')
		
		fig_diff = matplotlib.pyplot.figure(figsize=(7,7))
		ax_diff = fig_diff.add_subplot(111)
		n, bins,_ = ax_diff.hist(self.difference, max(self.difference) + 1, range=(-0.5,max(self.difference)+0.5),color="slateblue",fill=True,histtype='bar',align='mid')
		ax_diff.set_xlabel('difference in s')
		ax_diff.set_ylabel('number of transfers')
		ax_diff.set_title('Difference between waiting and starting time of transfers')			
		ax_diff.set_xlim(min(bins),max(bins))

		# save figure
                plotname = hf.downloadService.getArchivePath( self.run, self.instance_name + "_dcacheinfo.png")
                fig.savefig(plotname, dpi=91, bbox_inches="tight")
		fig_diff.savefig(plotname.replace(".png","_timedifferences.png"), dpi=91, bbox_inches="tight")
                return plotname