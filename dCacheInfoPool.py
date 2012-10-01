# -*- coding: utf-8 -*-
#
# Copyright 2012 Institut für Experimentelle Kernphysik - Karlsruher Institut für Technologie
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

import hf, lxml, logging, datetime
import parser
from sqlalchemy import *
from lxml import etree

class dCacheInfoPool(hf.module.ModuleBase):
    config_keys = {
        'global_critical_ratio': ('ratio determines module status: (sum of free space)/(sum of total space)', '0.1'),
        'local_critical_ratio': ('ratio determines pool status: pool free/total', '0.02'),
        'global_warning_ratio': ('ratio determines module status: (sum of free space)/(sum of total space)', '0.15'),
        'local_warning_ratio': ('ratio determines pool status: pool free/total', '0.05'),
        'global_critical_poolcriticals': ('module status is critical if more than this amount of pools are  critical pools', '1'),
        'global_critical_poolwarnings': ('module status is critical if more than this amount of pools are  warning pools', '4'),
        'global_warning_poolcriticals': ('module status is warning if more than this amount of pools are  critical pools', '0'),
        'global_warning_poolwarnings': ('module status is warning if more than this amount of pools are  warning pools', '0'),
        'poolgroups': ('name of the pools, a list is possible', ' cms-disk-only-pools'),
        'categories': ('name of the categories to be extracted, poolname and status will always be generated', 'total,free,precious,removable'),
        'unit': ('This should be GiB or TiB', 'TiB'),
        'source_xml': ('link to the source file', 'both||http://adm-dcache.gridka.de:2286/info/pools'),
        'special_overview': ('this parameter allows you to add several new lines to the overview, you have 4 variables(total, free, precious, removable) you can use to define the new line. this adds the line example with the value calculated the way described after =', 'example[%]=(r+t)/(f-p)*100'),
        'special_details': ('it is equal to special_overview but adds a new column for details', 'example=(r+t)/(f-p)'),
    }
    config_hint = ''
    
    table_columns = [
        Column('num_pools', INT),
        Column('crit_pools', INT),
        Column('warn_pools', INT),
        Column('total', INT),
        Column('free', INT),
        Column('precious', INT),
        Column('removable', INT),
        Column('special_overview', TEXT),
        Column('special_details', TEXT),
        Column('unit', TEXT),
    ], []

    subtable_columns = {
        "details": ([
            Column('poolname', TEXT),
            Column('total', FLOAT),
            Column('free', FLOAT),
            Column('precious', FLOAT),
            Column('removable', FLOAT),
            Column('status', FLOAT),
        ], []),
    }
    
    
    def prepareAcquisition(self):
        # read configuration
        try:
            self.global_critical_ratio = float(self.config['global_critical_ratio'])
            self.local_critical_ratio = float(self.config['local_critical_ratio'])
            self.global_warning_ratio = float(self.config['global_warning_ratio'])
            self.local_warning_ratio = float(self.config['local_warning_ratio'])
            self.global_critical_poolcriticals = int(self.config['global_critical_poolcriticals'])
            self.global_critical_poolwarnings = int(self.config['global_critical_poolwarnings'])
            self.global_warning_poolcriticals = int(self.config['global_warning_poolcriticals'])
            self.global_warning_poolwarnings = int(self.config['global_warning_poolwarnings'])
            self.poolgroups = self.config['poolgroups'].strip().split(',')
            self.unit = self.config['unit']
            self.special_overview = self.config['special_overview']
            self.special_details = self.config['special_details']
        except KeyError, e:
            raise hf.exceptions.ConfigError('Required parameter "%s" not specified' % str(e))

        if 'source_xml' not in self.config: raise hf.exceptions.ConfigError('source_xml option not set')
        self.source_xml = hf.downloadService.addDownload(self.config['source_xml'])
        self.details_db_value_list = []

    def extractData(self):
        data = {}
        if self.unit != 'GiB' and self.unit != 'TiB':
            self.logger.error(self.unit + ' is not an accepted unit, using TiB instead!')
            self.unit = 1024 * 1024 * 1024 * 1024.0
            data['unit'] = 'TiB'
        elif self.unit == 'GiB':
            self.unit = 1024 * 1024 * 1024.0
            data['unit'] = 'GiB'
        else:
            self.unit = 1024 * 1024 * 1024 * 1024.0
            data['unit'] = 'TiB'
        data['source_url'] = self.source_xml.getSourceUrl()
        data['status'] = 1
        data['special_overview'] = self.special_overview
        data['special_details'] = self.special_details

        #if self.source_xml.errorOccured() or not self.source_xml.isDownloaded():
            #data['error_string'] = 'Source file was not downloaded. Reason: %s' % self.source_xml.error
            #data['status'] = -1
            #return data

        source_tree = etree.parse(open('/usr/users/mschmitt/HappyFace3/modules/Test.xml'))
        root = source_tree.getroot()
        
        for pools in root:
            if pools.tag == '{http://www.dcache.org/2008/01/Info}pools':
                for pool in pools:
                    for poolgroups in pool:
                        if poolgroups.tag == '{http://www.dcache.org/2008/01/Info}poolgroups':
                            accept = 'false'
                            for poolgroupref in poolgroups:
                                if poolgroupref.get('name') in self.poolgroups:
                                    accept = 'true'
                                    break
                            if accept == 'true':
                                for space in pool:
                                    if space.tag == '{http://www.dcache.org/2008/01/Info}space':
                                        appending = {}
                                        appending['poolname'] = pool.get('name')
                                        appending['status'] = 1.0
                                        appending['total'] = 0
                                        appending['free'] = 0
                                        appending['precious'] = 0
                                        appending['removable'] = 0
                                        for metric in space:
                                            if metric.get('name') == 'total':
                                                appending['total'] = float(metric.text) / self.unit
                                            elif metric.get('name') == 'free':
                                                appending['free'] = float(metric.text) / self.unit
                                            elif metric.get('name') == 'precious':
                                                appending['precious'] = float(metric.text) / self.unit
                                            elif metric.get('name') == 'removable':
                                                appending['removable'] = float(metric.text) / self.unit
                                        self.details_db_value_list.append(appending)
        data['num_pools'] = 0
        data['crit_pools'] = 0
        data['warn_pools'] = 0
        data['total'] = 0
        data['free'] = 0
        data['precious'] = 0
        data['removable'] = 0        
        for i,pool in enumerate(self.details_db_value_list):
            data['num_pools'] += 1
            data['total'] += pool['total']
            data['free'] += pool['free']
            data['precious'] += pool['precious']
            data['removable'] += pool['removable']
            
            if pool['free'] / pool['total'] <= self.local_critical_ratio:
                pool['status'] = 0.0
                data['crit_pools'] += 1
            elif pool['free'] / pool['total'] <= self.local_warning_ratio:
                pool['status'] = 0.5
                data['warn_pools'] += 1
            else:
                pool['status'] = 1.0

        if data['free'] / data['total'] <= self.global_critical_ratio or data['crit_pools'] > self.global_critical_poolcriticals or data['warn_pools'] > self.global_critical_poolwarnings:
            data['status'] = 0.0
        elif data['free'] / data['total'] <= self.global_warning_ratio or data['crit_pools'] > self.global_warning_poolcriticals or data['warn_pools'] > self.global_warning_poolwarnings:
            data['status'] = 0.5

        return data
    
    def fillSubtables(self, parent_id):
        self.subtables['details'].insert().execute([dict(parent_id=parent_id, **row) for row in self.details_db_value_list])
    
    def getTemplateData(self):
        data = hf.module.ModuleBase.getTemplateData(self)

        details_list = self.subtables['details'].select().where(self.subtables['details'].c.parent_id==self.dataset['id']).execute().fetchall()
        details_list = map(lambda x: dict(x), details_list)
        self.logger.error(self.dataset)
        
        
        special_details = self.dataset['special_details']
        special_overview = self.dataset['special_overview']
        special_overview = self.dataset['special_overview'].split(',')
        special_details = self.dataset['special_details'].split(',')
        self.logger.error(special_overview)
        self.logger.error(special_details)
        
        for i,special in enumerate(special_overview):
            if '=' in special:
                special_overview[i] = special.split('=')
                special_overview[i][1] = parser.expr(special_overview[i][1]).compile()
            else:
                pass
        
        for i,special in enumerate(special_details):
            if '=' in special:
                special_details[i] = special.split('=')
                special_details[i][1] = parser.expr(special_details[i][1]).compile()
            else:
                pass
            
        self.logger.error(special_overview)
        self.logger.error(special_details)
        overview_list = []
        t = self.dataset['total']
        p = self.dataset['precious']
        f = self.dataset['free']
        r = self.dataset['removable']
        overview_list.append(['Pools', self.dataset['num_pools']])
        overview_list.append(['Pools with status warning', self.dataset['warn_pools']])
        overview_list.append(['Pools with status critical', self.dataset['crit_pools']])
        overview_list.append(['Pools with status warning [%]', float(self.dataset['warn_pools']) / self.dataset['num_pools']*100])
        overview_list.append(['Pools with status critical [%]', float(self.dataset['crit_pools']) / self.dataset['num_pools']*100])
        overview_list.append(['Total Space [' + self.dataset['unit'] + ']', t])
        overview_list.append(['Free Space [' + self.dataset['unit'] + ']', f])
        overview_list.append(['Used Space [' + self.dataset['unit'] + ']', t - f])
        overview_list.append(['Precious Space [' + self.dataset['unit'] + ']', p])
        overview_list.append(['Removable Space [' + self.dataset['unit'] + ']', r])
        for i,special in enumerate(special_overview):
            try:
                overview_list.append([special[0], eval(special[1])])
            except:
                overview_list.append([special[0], 'matherror'])
        
        details_finished_list = []
        help_appending = []
        help_appending.append('none')
        help_appending.append('Poolname')
        help_appending.append('Total Space [' + self.dataset['unit'] + ']')
        help_appending.append('Free Space [' + self.dataset['unit'] + ']')
        help_appending.append('Used Space [' + self.dataset['unit'] + ']')
        help_appending.append('Precious Space [' + self.dataset['unit'] + ']')
        help_appending.append('Removable Space [' + self.dataset['unit'] + ']')
        for i,special in enumerate(special_details):
            help_appending.append(special[0])
        details_finished_list.append(help_appending)
        
        for i,pool in enumerate(details_list):
            help_appending= []
            if pool['status'] == 1.0:
                help_appending.append('ok')
            elif pool['status'] == 0.5:
                help_appending.append('warning')
            else:
                help_appending.append('critical')
                
            r = pool['removable']
            t = pool['total']
            f = pool['free']
            p = pool['precious']
            
            help_appending.append(pool['poolname'])
            help_appending.append(t)
            help_appending.append(f)
            help_appending.append(t-f)
            help_appending.append(p)
            help_appending.append(r)
            
            for i,special in enumerate(special_details):
                try:
                    help_appending.append(eval(special[1]))
                except:
                    help_appending.append('matherror')
                
            details_finished_list.append(help_appending)
            
        data['details'] = details_finished_list
        data['overview'] = overview_list
        
        return data
