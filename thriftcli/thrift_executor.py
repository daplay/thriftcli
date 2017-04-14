# Copyright Notice:
# Copyright 2017, Fitbit, Inc.
# Licensed under the Apache License, Version 2.0 (the "License"); you
# may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import shutil
import subprocess
import sys
import urlparse

from thrift.protocol import TBinaryProtocol
from thrift.transport import TSocket
from thrift.transport import TTransport

from .thrift_cli_error import ThriftCLIError
from .thrift_parser import ThriftParser


class ThriftExecutor(object):
    """ This class handles connecting to and communicating with the Thrift server. """

    def __init__(self, thrift_path, server_address, service_reference, thrift_dir_paths=None):
        """ Opens a connection with the server and generates then imports the thrift-defined python code.

        :param thrift_path: the path to the Thrift file defining the service being requested
        :param server_address: the address to the server implementing the service
        :param service_reference: the namespaced service name in the format <file-name>.<service-name>
        :param thrift_dir_paths: a list of paths to directories containing Thrift file dependencies

        """
        self._thrift_path = thrift_path
        self._server_address = server_address
        self._thrift_dir_paths = thrift_dir_paths if thrift_dir_paths is not None else []
        self._service_reference = service_reference
        self._open_connection(server_address)
        self._generate_and_import_packages()

    def run(self, method_name, request_args):
        """ Executes a method on the connected server and returns its result.

        :param method_name: the name of the method to call
        :type method_name: str
        :param request_args: keyword arguments to pass into method call, acting as a request body
        :type request_args: dict
        :return: the result of the method call

        """
        method = self._get_method(method_name)
        return method(**request_args)

    def cleanup(self, remove_generated_src=False):
        """ Deletes the gen-py code and closes the transport with the server.

        :param remove_generated_src: whether or not to delete the generated source

        """
        if remove_generated_src:
            self._remove_dir('gen-py')
        if self._transport:
            self._transport.close()

    @staticmethod
    def _remove_dir(path):
        """ Recursively removes a directory and ignores if it didn't exist.

        :param path: the directory to remove

        """
        try:
            shutil.rmtree(path)
        except OSError:
            pass

    def _generate_and_import_packages(self):
        """ Generates and imports the python modules defined by the thrift code.

        This method does the following:
        1. Runs a shell process to generate the python code from the Thrift file
        2. Adds the generated source to the python process' path
        3. Imports the generated source package into this python process

        """
        thrift_dir_options = ''.join([' -I %s' % thrift_dir_path for thrift_dir_path in self._thrift_dir_paths])
        command = 'thrift -r%s --gen py %s' % (thrift_dir_options, self._thrift_path)
        if subprocess.call(command, shell=True) != 0:
            raise ThriftCLIError('Thrift generation command failed: \'%s\'' % command)
        sys.path.append('gen-py')
        self._import_package(ThriftParser.get_package_name(self._thrift_path))

    def _get_method(self, method_name):
        """ Returns the python method generated for the given endpoint.

        :param method_name: the name of the method to retrieve
        :returns: the python method that can be called to execute the Thrift RPC
        :rtype: method

        """
        class_name = 'Client'
        client_constructor = getattr(sys.modules[self._service_reference], class_name)
        client = client_constructor(self._protocol)
        try:
            method = getattr(client, method_name)
        except AttributeError:
            raise ThriftCLIError('\'%s\' service has no method \'%s\'' % (self._service_reference, method_name))
        return method

    def _open_connection(self, address):
        """ Opens a connection with a server address.

        :param address: the address of the server to connect to

        """
        (url, port) = self._parse_address_for_hostname_and_port(address)
        self._transport = TSocket.TSocket(url, port)
        self._transport = TTransport.TFramedTransport(self._transport)
        self._protocol = TBinaryProtocol.TBinaryProtocol(self._transport)
        self._transport.open()

    @staticmethod
    def _parse_address_for_hostname_and_port(address):
        """ Extracts the hostname and port from a url address.

        :param address: an address to parse
        :returns: the hostname and port of the address
        :rtype: tuple of (str, str)

        """
        if '//' not in address:
            address = '//' + address
        url_obj = urlparse.urlparse(address)
        return url_obj.hostname, url_obj.port

    @staticmethod
    def _import_package(package_name):
        """ Imports a package generated by thrift code.

        :param package_name: the name of the package to import, which must be located somewhere on sys.path

        """
        package = __import__(package_name, globals())
        modules = package.__all__
        for module in modules:
            module_name = '.'.join([package_name, module])
            __import__(module_name, globals())
