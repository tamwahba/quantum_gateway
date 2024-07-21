from http import HTTPStatus
import unittest
from unittest import mock
import json
import hashlib

from requests import status_codes
import requests
from requests.api import request
import requests_mock
import re

from quantum_gateway import DeviceInfo, Gateway, Gateway1100, Gateway3100,\
    QuantumGatewayScanner

G3100_LOGIN_STATUS_MATCHER = re.compile('^.*/loginStatus.cgi$')


class TestScanner(unittest.TestCase):

    @requests_mock.Mocker()
    def test_detects_g3100(self, m):
        m.get(G3100_LOGIN_STATUS_MATCHER)
        with mock.patch('quantum_gateway.Gateway3100') as MockGateway3100:
            scanner = QuantumGatewayScanner("192.168.1.1", "password")
            MockGateway3100.assert_called_once_with("192.168.1.1", "password")

    @requests_mock.Mocker()
    def test_defaults_to_g1100(self, m):
        m.get(G3100_LOGIN_STATUS_MATCHER, status_code=HTTPStatus.NOT_FOUND)
        with mock.patch('quantum_gateway.Gateway1100') as MockGateway1100:
            scanner = QuantumGatewayScanner("192.168.1.1", "password")
            MockGateway1100.assert_called_once_with("192.168.1.1", "password", True)

    def test_successful_init(self):
        with mock.patch.object(QuantumGatewayScanner, "_get_gateway") as mock_get_gateway:
            mock_gateway = mock.create_autospec(Gateway)
            mock_gateway.check_auth.return_value = True
            mock_get_gateway.return_value = mock_gateway

            scanner = QuantumGatewayScanner("192.168.1.1", "password")
            self.assertTrue(scanner.success_init)

    def test_failed_init(self):
        with mock.patch.object(QuantumGatewayScanner, "_get_gateway") as mock_get_gateway:
            mock_gateway = mock.create_autospec(Gateway)
            mock_gateway.check_auth.return_value = False
            mock_get_gateway.return_value = mock_gateway

            scanner = QuantumGatewayScanner("192.168.1.1", "password")
            mock_gateway.check_auth.assert_called_once()
            self.assertFalse(scanner.success_init)

    def test_get_connected_devices(self):
        with mock.patch.object(QuantumGatewayScanner, "_get_gateway") as mock_get_gateway:
            mock_gateway = mock.create_autospec(Gateway)
            mock_gateway.check_auth.return_value = True
            mock_gateway.get_connected_devices.return_value = {"mac_address": "hostname"}
            mock_get_gateway.return_value = mock_gateway

            scanner = QuantumGatewayScanner("192.168.1.1", "password")
            self.assertCountEqual(scanner.scan_devices(), ["mac_address"])

    def test_get_device_name(self):
        with mock.patch.object(QuantumGatewayScanner, "_get_gateway") as mock_get_gateway:
            mock_gateway = mock.create_autospec(Gateway)
            mock_gateway.check_auth.return_value = True
            mock_gateway.get_connected_devices.return_value = {"mac_address": "hostname"}
            mock_get_gateway.return_value = mock_gateway

            scanner = QuantumGatewayScanner("192.168.1.1", "password")
            scanner.scan_devices()
            self.assertEqual(scanner.get_device_name("mac_address"), "hostname")

    def test_get_all_devices(self):
        devices = {"mac_address": DeviceInfo("mac_address", "hostname", True, None)}
        with mock.patch.object(QuantumGatewayScanner, "_get_gateway") as mock_get_gateway:
            mock_gateway = mock.create_autospec(Gateway)
            mock_gateway.check_auth.return_value = True
            mock_gateway.get_all_devices.return_value = devices
            mock_get_gateway.return_value = mock_gateway

            scanner = QuantumGatewayScanner("192.168.1.1", "password")
            self.assertEqual(scanner.get_all_devices(), devices)


@requests_mock.Mocker()
class TestGateway1100(unittest.TestCase):
    DEVICES_MATCHER = re.compile('^.*/api/devices$')
    LOGIN_MATCHER = re.compile('^.*/api/login$')
    TOKEN = 'TEST_TOKEN'
    PASSWORD_SALT = 'TEST_SALT'
    CORRECT_PASSWORD = 'correct'
    WRONG_PASSWORD = 'wrong'
    ALL_DEVICES = {
        '00:11:22:33:44:55': DeviceInfo('00:11:22:33:44:55', 'iphone', True, "192.168.1.1"),
        '00:00:00:00:00:00': DeviceInfo('00:00:00:00:00:00', 'computer', True, "192.168.1.2"),
        '11:11:11:11:11:11': DeviceInfo('11:11:11:11:11:11', 'disconnected', False, "fdde:6cb2:070a:219a:a092:5969:be0d:19ef"),
        '11:11:11:22:22:22': DeviceInfo('11:11:11:22:22:22', 'disconnected-empty-ips', False, None),
        '33:33:33:22:22:22': DeviceInfo('33:33:33:22:22:22', 'disconnected-missing-ips', False, None),
    }
    CONNECTED_DEVICES = {'00:11:22:33:44:55': 'iphone', '00:00:00:00:00:00': 'computer'}
    SERVER_CONNECTED_DEVICES_RESPONSE = '''[
        {"mac": "00:11:22:33:44:55", "name": "iphone", "status": true, "ipAddress": "192.168.1.1", "ipv6Address": ""},
        {"mac": "00:00:00:00:00:00", "name": "computer", "status": true, "ipAddress": "192.168.1.2", "ipv6Address": "fdde:6cb2:070a:219a:a092:5969:be0d:19ee"},
        {"mac": "11:11:11:11:11:11", "name": "disconnected", "status": false, "ipAddress": "", "ipv6Address": "fdde:6cb2:070a:219a:a092:5969:be0d:19ef"},
        {"mac": "11:11:11:22:22:22", "name": "disconnected-empty-ips", "status": false, "ipAddress": "", "ipv6Address": ""},
        {"mac": "33:33:33:22:22:22", "name": "disconnected-missing-ips", "status": false}
    ]'''

    logged_in = False

    def setUp(self):
        self.logged_in = False

    def test_login_success(self, m):
        self.setup_matcher(m)

        host = '192.168.1.2'
        password = self.CORRECT_PASSWORD
        gateway = Gateway1100(host, password)

        self.assertTrue(gateway.check_auth())

    def test_login_fail(self, m):
        self.setup_matcher(m)

        host = '192.100.100.5'
        password = self.WRONG_PASSWORD
        gateway = Gateway1100(host, password)

        self.assertFalse(gateway.check_auth())

    def test_get_connected_devices(self, m):
        self.setup_matcher(m)

        host = 'mywifigateway.com'
        password = self.CORRECT_PASSWORD

        gateway = Gateway1100(host, password)

        gateway.check_auth()
        self.assertEqual(gateway.get_connected_devices(), self.CONNECTED_DEVICES)

    def test_get_all_devices(self, m):
        self.setup_matcher(m)

        host = 'mywifigateway.com'
        password = self.CORRECT_PASSWORD

        gateway = Gateway1100(host, password)

        gateway.check_auth()
        self.assertEqual(gateway.get_all_devices(), self.ALL_DEVICES)


    def setup_matcher(self, m):
        def devices_callback(request, context):
            if self.is_logged_in(request):
                context.status_code = 200
                return self.SERVER_CONNECTED_DEVICES_RESPONSE
            else:
                context.status_code = 401

        def password_callback(request, context):
            if self.is_correct_password(request):
                context.status_code = 200
                self.logged_in = True
            else:
                context.status_code = 401
            context.headers['set-cookie'] = 'XSRF-TOKEN=' + self.TOKEN

        m.get(self.DEVICES_MATCHER, text=devices_callback)
        m.get(self.LOGIN_MATCHER, status_code=200, json={'passwordSalt': self.PASSWORD_SALT})
        m.post(self.LOGIN_MATCHER, text=password_callback)

    def is_logged_in(self, request):
        return self.logged_in and request.headers.get('X-XSRF-TOKEN') == self.TOKEN

    def is_correct_password(self, request):
        hash = hashlib.sha512()
        hash.update((self.CORRECT_PASSWORD + self.PASSWORD_SALT).encode('ascii'))
        expected_encoded_password = hash.hexdigest()
        actual_encoded_password = json.loads(request.body)['password']

        return actual_encoded_password == expected_encoded_password

@requests_mock.Mocker()
class TestGateway3100(unittest.TestCase):

    LOGIN_MATCHER = re.compile('^.*/login.cgi$')
    DEVICE_INFO_MATCHER = re.compile('^.*/cgi_owl.js$')
    LOGOUT_MATCHER = re.compile('^.*/logout.cgi$')

    LOGGED_OUT_STATUS_JSON = {"islogin": "0", "loginToken": ""}
    LOGGED_IN_STATUS_JSON = {
        "islogin": "1",
        "token": "token_value",
        "loginToken": "login_token"
    }

    def setUp(self):
        self.host = "192.168.23.16"
        self.password = "password"

    def test_login_success(self, m):
        self._match_successful_login(m)
        self._match_logout(m)

        gateway = Gateway3100(self.host, self.password)

        self.assertTrue(gateway.check_auth())

    def test_login_fail(self, m):
        m.get(G3100_LOGIN_STATUS_MATCHER, json=self.LOGGED_OUT_STATUS_JSON)
        m.post(self.LOGIN_MATCHER, status_code=HTTPStatus.FORBIDDEN, json={})
        self._match_logout(m)

        gateway = Gateway3100(self.host, self.password)

        self.assertFalse(gateway.check_auth())

    def test_get_connected_devices(self, m):
        device_info_response_text = """
        addROD("known_device_list", { "known_devices": [{ "mac": "xx:xx:xx:xx:xx:xx", "hostname": "active_device", "activity": 1 },{ "mac": "xx:xx:xx:xx:xx:ab", "hostname": "inactive_device", "activity": 0 }] });
        """

        self._match_successful_login(m)
        m.get(self.DEVICE_INFO_MATCHER, text=device_info_response_text)
        self._match_logout(m)

        gateway = Gateway3100(self.host, self.password)

        self.assertCountEqual(gateway.get_connected_devices(), {"xx:xx:xx:xx:xx:xx": "hostname"})

    def test_get_all_devices(self, m):
        device_info_response_text = """
        addROD("known_device_list", { "known_devices": [{ "mac": "xx:xx:xx:xx:xx:xx", "hostname": "active_device", "activity": 1 },{ "mac": "xx:xx:xx:xx:xx:ab", "hostname": "inactive_device", "activity": 0 }] });
        """

        self._match_successful_login(m)
        m.get(self.DEVICE_INFO_MATCHER, text=device_info_response_text)
        self._match_logout(m)

        gateway = Gateway3100(self.host, self.password)

        self.assertEqual(gateway.get_all_devices(), {
            "xx:xx:xx:xx:xx:xx": DeviceInfo("xx:xx:xx:xx:xx:xx", "active_device", True, None),
            "xx:xx:xx:xx:xx:ab": DeviceInfo("xx:xx:xx:xx:xx:ab", "inactive_device", False, None),
        })

    def _match_successful_login(self, m):
        m.get(G3100_LOGIN_STATUS_MATCHER, json=self.LOGGED_OUT_STATUS_JSON)
        def check_login_data(request, context):
            self.assertEqual(request.data, {
                "luci_username": "",
                "luci_password": "",
            })
        m.post(self.LOGIN_MATCHER, text=check_login_data)
        m.get(G3100_LOGIN_STATUS_MATCHER, json=self.LOGGED_IN_STATUS_JSON)

    def _match_logout(self, m):
        m.post(self.LOGOUT_MATCHER)

if __name__ == '__main__':
    unittest.main()
