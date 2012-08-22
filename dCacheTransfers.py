# -*- coding: utf-8 -*-
import hf, lxml, logging, datetime
from sqlalchemy import *
import math
class dCacheTransfers(hf.module.ModuleBase):

    def prepareAcquisition(self):
        
        try:
            self.speed_warning_limit = int(self.config['speed_warning_limit'])
            self.speed_critical_limit = int(self.config['speed_critical_limit'])
            self.time_warning_limit = int(self.config['time_warning_limit'])
            self.time_critical_limit = int(self.config['time_critical_limit'])
            self.rating_ratio = float(self.config['rating_ratio'])
            self.rating_threshold = int(self.config['rating_threshold'])
            self.source = hf.downloadService.addDownload(self.config['source_url']) 
            self.details_db_value_list = []
        except KeyError, ex:
            raise hf.exceptions.ConfigError('Required parameter "%s" not specified' % str(e))
        
    def extractData(self):
        data = {}
        data['source_url'] = self.source.getSourceUrl()
        data['below_speed_warning_limit'] = 0
        data['below_speed_critical_limit'] = 0
        data['exceed_time_warning_limit'] = 0
        data['exceed_time_critical_limit'] = 0
        data['total_transfers'] = 0
        data['warning_transfers'] = 0
        data['critical_transfers'] = 0
        fobj = open(self.source.getTmpPath(), 'r')
        speed_sum = 0
        for line in fobj:
            line_split = line.split(' ')
            appender = {}
            if len(line_split) <= 11:
                continue
            if line_split[3] == 'GFtp-2':
                if 'f01-' in line_split[7]:
                    keep = str(line_split[9]) + str(line_split[10]) + str(line_split[11])
                    trash = line_split.pop(9)
                    trash = line_split.pop(10)
                    line_split[9] = keep
                else:
                    continue
            if line_split[11] == 'RUNNING':
                appender['protocol'] = line_split[3]
                appender['pnfsid'] = line_split[6]
                appender['pool'] = line_split[7]
                appender['host'] = line_split[8]
                appender['status_text'] = line_split[9]
                appender['since'] = int(line_split[10])
                appender['transferred'] = float(line_split[13]) / 1024.0 / 1024.0 / 1024.0
                appender['speed'] = float(line_split[14]) * 1000.0 / 1024.0
                data['total_transfers'] += 1
                speed_sum += float(line_split[14]) * 1000.0 / 1024.0
                if int(appender['speed']) <= self.speed_critical_limit:
                    appender['status'] = 0.0
                    data['below_speed_critical_limit'] += 1
                elif int(appender['speed']) <= self.speed_warning_limit:
                    appender['status'] = 0.5
                    data['below_speed_warning_limit'] += 1
                else:
                    appender['status'] = 1.0
                    
                if appender['since'] >= (self.time_critical_limit * 3600 * 1000) and appender['status'] != 0.0:
                    data['status'] = 0.0
                    data['exceed_time_critical_limit'] += 1
                elif appender['since'] >= (self.time_warning_limit * 3600 * 1000) and appender['status'] == 1.0:
                    data['status'] = 0.5
                    data['exceed_time_warning_limit'] += 1
                self.details_db_value_list.append(appender)
        data['warning_transfers'] = data['below_speed_warning_limit'] + data['exceed_time_warning_limit']
        data['critical_transfers'] = data['below_speed_critical_limit'] + data['exceed_time_critical_limit']
        
        data['speed_average'] = int(speed_sum / data['total_transfers'])
        speed_avg = data['speed_average']
        speed_delta = 0
        total_jobs = data['total_transfers']
        for i, item in enumerate(self.details_db_value_list):
            speed_delta += 1.0 /((float(total_jobs) - 1.0) * float(total_jobs)) * (float(item['speed']) - float(speed_avg)) ** 2
        data['speed_stdev'] = int(math.sqrt(speed_delta))
        
        if float(data['warning_transfers']) / data['total_transfers'] >= self.rating_ratio and data['total_transfers'] >= 10:
            data['status'] = 0.5
        elif float(data['warning_transfers'] + data['critical_transfers']) / data['total_transfers'] >= self.rating_ratio and data['total_transfers'] >= 10:
            data['status'] = 0.5
        elif float(data['critical_transfers']) / data['total_transfers'] >= self.rating_ratio and data['total_transfers'] >= 10:
            data['status'] = 0.0
        else:
            data['status'] = 1.0
        return data
    
    def fillSubtables(self, parent_id):
        details_table.insert().execute([dict(parent_id=parent_id, **row) for row in self.details_db_value_list])
    
    def getTemplateData(self):
        data = hf.module.ModuleBase.getTemplateData(self)
        details_list = details_table.select().where(details_table.c.parent_id==self.dataset['id']).execute().fetchall()
        data['details'] = map(dict, details_list)
        
        for i,item in enumerate(data['details']):
            if item['status'] == 1.0:
                data['details'][i]['status'] = 'ok'
            elif item['status'] == 0.5:
                data['details'][i]['status'] = 'warning'
            else:
                data['details'][i]['status'] = 'critical'
            store = item['since']
            data['details'][i]['since'] = str('%02i' %int(store / (24 * 3600 * 1000))) + ':' + str('%02i' %int((store % (24 * 3600 * 1000)) / (3600 * 1000))) + ':' + str('%02i' %int(((store % (24 * 3600 * 1000)) % (3600 * 1000) / (60 * 1000)))) + ':' + str('%02i' %int((((store % (24 * 3600 * 1000)) % (3600 * 1000)) % (60 * 1000)) / 1000))
                
        return data
				
				
module_table = hf.module.generateModuleTable(dCacheTransfers, "dcache_transfers", [
    Column('speed_average', INT),
    Column('speed_stdev', INT),
    Column('below_speed_warning_limit', INT),
    Column('below_speed_critical_limit', INT),
    Column('exceed_time_warning_limit', INT),
    Column('exceed_time_critical_limit', INT),
    Column('total_transfers', INT),
    Column('warning_transfers', INT),
    Column('critical_transfers', INT)
])        

details_table = hf.module.generateModuleSubtable('details', module_table, [
    Column('protocol', TEXT),
    Column('pnfsid', TEXT),
    Column('pool', TEXT),
    Column('host', TEXT),
    Column('status_text', TEXT),
    Column('since', INT),
    Column('transferred', FLOAT),
    Column('speed', INT),
    Column('status', FLOAT)
])

hf.module.addModuleClass(dCacheTransfers)
