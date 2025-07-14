# Ansible callback plugin to log task execution to MongoDB
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import datetime
import socket
import os
import psutil
from pymongo import MongoClient
from ansible.plugins.callback import CallbackBase
import traceback
import sys

def log_debug(msg):
    try:
        with open('/tmp/mongo_logger_debug.log', 'a') as f:
            f.write(f"{datetime.datetime.utcnow().isoformat()} {msg}\n")
    except Exception as e:
        pass

DOCUMENTATION = r'''
    callback: mongo_logger
    type: notification
    short_description: Log Ansible task results to MongoDB
    description:
      - This callback logs task execution details to a MongoDB database.
    requirements:
      - pymongo
      - psutil
'''

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'mongo_logger'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super(CallbackModule, self).__init__()
        try:
            log_debug('mongo_logger __init__ called')
            self.client = MongoClient(os.environ.get('MONGO_URI', 'mongodb://admin:mongo2025@192.168.68.101:27017/'))
            self.db = self.client['ansible_logs']
            self.collection = self.db['task_logs']
            self.task_start_times = {}
            log_debug('mongo_logger connected to MongoDB')
        except Exception as e:
            log_debug(f'Exception in __init__: {e}\n{traceback.format_exc()}')
            pass

    def _get_resource_usage(self):
        try:
            usage = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=None)
            disk = psutil.disk_usage('/')
            threads = psutil.cpu_count()
            return {
                'cpu_percent': cpu,
                'memory_total': usage.total,
                'memory_used': usage.used,
                'memory_percent': usage.percent,
                'disk_total': disk.total,
                'disk_used': disk.used,
                'disk_percent': disk.percent,
                'threads': threads
            }
        except Exception as e:
            pass 
            return {}

    def v2_runner_on_ok(self, result):
        self._log_task_result(result, 'ok')

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self._log_task_result(result, 'failed')

    def v2_runner_on_skipped(self, result):
        self._log_task_result(result, 'skipped')

    def v2_runner_on_unreachable(self, result):
        self._log_task_result(result, 'unreachable')

    def _log_task_result(self, result, status):
        try:
            log_debug(f'_log_task_result called for task: {getattr(result._task, "get_name", lambda: "unknown")()} with status: {status}')
            task = result._task
            playbook_name = None
            try:
                if hasattr(task, 'play') and hasattr(task.play, 'get_name'):
                    playbook_name = task.play.get_name()
            except Exception:
                pass
            host_vars = result._host.vars if hasattr(result._host, 'vars') else {}
            log_entry = {
                'task_name': task.get_name(),
                'status': status,
                'stdout': result._result.get('stdout', None),
                'stderr': result._result.get('stderr', None),
                'changed': result._result.get('changed', None),
                'module': task.action if hasattr(task, 'action') else None,
                'role': task._role._role_name if hasattr(task, '_role') and task._role else None,
                'playbook': playbook_name,
                'start_time': self.task_start_times.get(task._uuid, None),
                'end_time': datetime.datetime.utcnow(),
                'duration': None,
                'host': result._host.get_name() if hasattr(result, '_host') else None,
                'resource_usage': self._get_resource_usage(),
                'product_name': host_vars.get('product_name', 'no_product'),
                'cycle_name': host_vars.get('cycle_name', 'no_cycle'),
                'build_id': host_vars.get('build_id', 'no_build'),
                'tester_name': host_vars.get('tester_name', 'no_tester'),
            }
            self.collection.insert_one(log_entry)
            log_debug(f'Inserted log entry for task: {task.get_name()}')
        except Exception as e:
            log_debug(f'Exception in _log_task_result: {e}\n{traceback.format_exc()}')
            pass 