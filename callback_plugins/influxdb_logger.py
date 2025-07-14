# Ansible callback plugin to log task execution to InfluxDB
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import datetime
import socket
import os
import psutil
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from ansible.plugins.callback import CallbackBase
import traceback

DOCUMENTATION = r'''
    callback: influxdb_logger
    type: notification
    short_description: Log Ansible task results to InfluxDB
    description:
      - This callback logs task execution details to an InfluxDB database.
    requirements:
      - influxdb-client
      - psutil
'''

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'influxdb_logger'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super(CallbackModule, self).__init__()
        try:
            self.url = os.environ.get('DB_URI')
            self.token = os.environ.get('INFLUXDB_TOKEN', 'mytoken')
            self.org = os.environ.get('INFLUXDB_ORG', 'myorg')
            self.bucket = os.environ.get('INFLUXDB_BUCKET', 'ansible_logs')
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.task_start_times = {}
        except Exception as e:
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
            task = result._task
            playbook_name = None
            try:
                if hasattr(task, 'play') and hasattr(task.play, 'get_name'):
                    playbook_name = task.play.get_name()
            except Exception:
                pass
            host_vars = result._host.vars if hasattr(result._host, 'vars') else {}
            resource_usage = self._get_resource_usage()
            point = Point("ansible_task") \
                .tag("task_name", task.get_name()) \
                .tag("status", status) \
                .tag("module", getattr(task, 'action', None)) \
                .tag("role", task._role._role_name if hasattr(task, '_role') and task._role else None) \
                .tag("playbook", playbook_name) \
                .tag("host", result._host.get_name() if hasattr(result, '_host') else None) \
                .tag("product_name", host_vars.get('product_name', 'no_product')) \
                .tag("cycle_name", host_vars.get('cycle_name', 'no_cycle')) \
                .tag("build_id", host_vars.get('build_id', 'no_build')) \
                .tag("tester_name", host_vars.get('tester_name', 'no_tester')) \
                .field("stdout", str(result._result.get('stdout', ''))) \
                .field("stderr", str(result._result.get('stderr', ''))) \
                .field("changed", bool(result._result.get('changed', False))) \
                .field("memory_total", resource_usage.get('memory_total', 0)) \
                .field("memory_used", resource_usage.get('memory_used', 0)) \
                .field("memory_percent", resource_usage.get('memory_percent', 0)) \
                .field("cpu_percent", resource_usage.get('cpu_percent', 0)) \
                .field("disk_total", resource_usage.get('disk_total', 0)) \
                .field("disk_used", resource_usage.get('disk_used', 0)) \
                .field("disk_percent", resource_usage.get('disk_percent', 0)) \
                .field("threads", resource_usage.get('threads', 0)) \
                .field("end_time", str(datetime.datetime.utcnow()))
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as e:
            pass 