#! /usr/bin/env python3

import atexit
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from hwilib.commands import process_commands

def start_bitcoind(bitcoind_path):
    datadir = tempfile.mkdtemp()
    bitcoind_proc = subprocess.Popen([bitcoind_path, '-regtest', '-datadir=' + datadir, '-noprinttoconsole'])
    def cleanup_bitcoind():
        bitcoind_proc.kill()
        shutil.rmtree(datadir)
    atexit.register(cleanup_bitcoind)
    # Wait for cookie file to be created
    while not os.path.exists(datadir + '/regtest/.cookie'):
        time.sleep(0.5)
    # Read .cookie file to get user and pass
    with open(datadir + '/regtest/.cookie') as f:
        userpass = f.readline().lstrip().rstrip()
    rpc = AuthServiceProxy('http://{}@127.0.0.1:18443'.format(userpass))

    # Wait for bitcoind to be ready
    ready = False
    while not ready:
        try:
            rpc.getblockchaininfo()
            ready = True
        except JSONRPCException as e:
            time.sleep(0.5)
            pass

    # Make sure there are blocks and coins available
    rpc.generatetoaddress(101, rpc.getnewaddress())
    return (rpc, userpass)

class DeviceTestCase(unittest.TestCase):
    def __init__(self, rpc, rpc_userpass, type, path, fingerprint, master_xpub, methodName='runTest'):
        super(DeviceTestCase, self).__init__(methodName)
        self.rpc = rpc
        self.rpc_userpass = rpc_userpass
        self.type = type
        self.path = path
        self.fingerprint = fingerprint
        self.master_xpub = master_xpub
        self.dev_args = ['-t', self.type, '-d', self.path]

    @staticmethod
    def parameterize(testclass, rpc, rpc_userpass, type, path, fingerprint, master_xpub):
        testloader = unittest.TestLoader()
        testnames = testloader.getTestCaseNames(testclass)
        suite = unittest.TestSuite()
        for name in testnames:
            suite.addTest(testclass(rpc, rpc_userpass, type, path, fingerprint, master_xpub, name))
        return suite

class TestDeviceConnect(DeviceTestCase):
    def test_enumerate(self):
        enum_res = process_commands(['enumerate'])
        found = False
        for device in enum_res:
            self.assertNotIn('error', device)
            if device['type'] == self.type and device['path'] == self.path and device['fingerprint'] == self.fingerprint:
                found = True
        self.assertTrue(found)

    def test_no_type(self):
        gmxp_res = process_commands(['getmasterxpub'])
        self.assertIn('error', gmxp_res)
        self.assertEqual(gmxp_res['error'], 'You must specify a device type or fingerprint for all commands except enumerate')
        self.assertIn('code', gmxp_res)
        self.assertEqual(gmxp_res['code'], -1)

    def test_path_type(self):
        gmxp_res = process_commands(['-t', self.type, '-d', self.path, 'getmasterxpub'])
        self.assertEqual(gmxp_res['xpub'], self.master_xpub)

    def test_fingerprint_autodetect(self):
        gmxp_res = process_commands(['-f', self.fingerprint, 'getmasterxpub'])
        self.assertEqual(gmxp_res['xpub'], self.master_xpub)

    def test_type_only_autodetech(self):
        gmxp_res = process_commands(['-t', self.type, 'getmasterxpub'])
        self.assertEqual(gmxp_res['xpub'], self.master_xpub)

class TestGetKeypool(DeviceTestCase):
    def setUp(self):
        self.rpc = AuthServiceProxy('http://{}@127.0.0.1:18443'.format(self.rpc_userpass))
        if '{}_test'.format(self.type) not in self.rpc.listwallets():
            self.rpc.createwallet('{}_test'.format(self.type), True)
        self.wrpc = AuthServiceProxy('http://{}@127.0.0.1:18443/wallet/{}_test'.format(self.rpc_userpass, self.type))
        self.wpk_rpc = AuthServiceProxy('http://{}@127.0.0.1:18443/wallet/'.format(self.rpc_userpass))
        if '--testnet' not in self.dev_args:
            self.dev_args.append('--testnet')

    def test_getkeypool_bad_args(self):
        result = process_commands(self.dev_args + ['getkeypool', '--sh_wpkh', '--wpkh', '0', '20'])
        self.assertIn('error', result)
        self.assertIn('code', result)
        self.assertEqual(result['code'], -7)

    def test_getkeypool(self):
        non_keypool_desc = process_commands(self.dev_args + ['getkeypool', '0', '20'])
        import_result = self.wpk_rpc.importmulti(non_keypool_desc)
        self.assertTrue(import_result[0]['success'])

        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '0', '20'])
        import_result = self.wpk_rpc.importmulti(keypool_desc)
        self.assertFalse(import_result[0]['success'])

        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getnewaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/44'/1'/0'/0/{}".format(i))

        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--internal', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getrawchangeaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/44'/1'/0'/1/{}".format(i))

        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--sh_wpkh', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getnewaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/49'/1'/0'/0/{}".format(i))
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--sh_wpkh', '--internal', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getrawchangeaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/49'/1'/0'/1/{}".format(i))

        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--wpkh', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getnewaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/84'/1'/0'/0/{}".format(i))
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--wpkh', '--internal', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getrawchangeaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/84'/1'/0'/1/{}".format(i))

        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--sh_wpkh', '--account', '3', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getnewaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/49'/1'/3'/0/{}".format(i))
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--sh_wpkh', '--internal', '--account', '3', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getrawchangeaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/49'/1'/3'/1/{}".format(i))
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--wpkh', '--account', '3', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getnewaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/84'/1'/3'/0/{}".format(i))
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--wpkh', '--internal', '--account', '3', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getrawchangeaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/84'/1'/3'/1/{}".format(i))

        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--path', 'm/0h/0h/4h/*', '0', '20'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        for i in range(0, 21):
            addr_info = self.wrpc.getaddressinfo(self.wrpc.getnewaddress())
            self.assertEqual(addr_info['hdkeypath'], "m/0'/0'/4'/{}".format(i))

        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--path', '/0h/0h/4h/*', '0', '20'])
        self.assertEqual(keypool_desc['error'], 'Path must start with m/')
        self.assertEqual(keypool_desc['code'], -7)
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--path', 'm/0h/0h/4h/', '0', '20'])
        self.assertEqual(keypool_desc['error'], 'Path must end with /*')
        self.assertEqual(keypool_desc['code'], -7)

class TestSignTx(DeviceTestCase):
    def setUp(self):
        self.rpc = AuthServiceProxy('http://{}@127.0.0.1:18443'.format(self.rpc_userpass))
        if '{}_test'.format(self.type) not in self.rpc.listwallets():
            self.rpc.createwallet('{}_test'.format(self.type), True)
        self.wrpc = AuthServiceProxy('http://{}@127.0.0.1:18443/wallet/{}_test'.format(self.rpc_userpass, self.type))
        self.wpk_rpc = AuthServiceProxy('http://{}@127.0.0.1:18443/wallet/'.format(self.rpc_userpass))
        if '--testnet' not in self.dev_args:
            self.dev_args.append('--testnet')

    def _test_signtx(self, input_type, multisig):
        # Import some keys to the watch only wallet and send coins to them
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--sh_wpkh', '30', '40'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        keypool_desc = process_commands(self.dev_args + ['getkeypool', '--keypool', '--sh_wpkh', '--internal', '30', '40'])
        import_result = self.wrpc.importmulti(keypool_desc)
        self.assertTrue(import_result[0]['success'])
        sh_wpkh_addr = self.wrpc.getnewaddress('', 'p2sh-segwit')
        wpkh_addr = self.wrpc.getnewaddress('', 'bech32')
        pkh_addr = self.wrpc.getnewaddress('', 'legacy')
        self.wrpc.importaddress(wpkh_addr)
        self.wrpc.importaddress(pkh_addr)

        # pubkeys to construct 2-of-3 multisig descriptors for import
        sh_wpkh_info = self.wrpc.getaddressinfo(sh_wpkh_addr)
        wpkh_info = self.wrpc.getaddressinfo(wpkh_addr)
        pkh_info = self.wrpc.getaddressinfo(pkh_addr)

        # Get origin info/key pair so wallet doesn't forget how to
        # sign with keys post-import
        pubkeys = [sh_wpkh_info['desc'][8:-2],\
                wpkh_info['desc'][5:-1],\
                pkh_info['desc'][4:-1]]

        sh_multi_desc = {'desc':'sh(multi(2,'+pubkeys[0]+','+pubkeys[1]+','+pubkeys[2]+'))', "timestamp":"now", "label":"shmulti"}
        sh_wsh_multi_desc = {'desc':'sh(wsh(multi(2,'+pubkeys[0]+','+pubkeys[1]+','+pubkeys[2]+')))', "timestamp":"now", "label":"shwshmulti"}
        # re-order pubkeys to allow import without "already have private keys" error
        wsh_multi_desc = {'desc':'wsh(multi(2,'+pubkeys[2]+','+pubkeys[1]+','+pubkeys[0]+'))', "timestamp":"now", "label":"wshmulti"}
        multi_result = self.wrpc.importmulti([sh_multi_desc, sh_wsh_multi_desc, wsh_multi_desc])
        self.assertTrue(multi_result[0]['success'])
        self.assertTrue(multi_result[1]['success'])
        self.assertTrue(multi_result[2]['success'])

        sh_multi_addr = self.wrpc.getaddressesbylabel("shmulti").popitem()[0]
        sh_wsh_multi_addr = self.wrpc.getaddressesbylabel("shwshmulti").popitem()[0]
        wsh_multi_addr = self.wrpc.getaddressesbylabel("wshmulti").popitem()[0]

        send_amount = 2
        number_inputs = 0
        # Single-sig
        if input_type == 'segwit' or input_type == 'all':
            self.wpk_rpc.sendtoaddress(sh_wpkh_addr, send_amount)
            self.wpk_rpc.sendtoaddress(wpkh_addr, send_amount)
            number_inputs += 2
        if input_type == 'legacy' or input_type == 'all':
            self.wpk_rpc.sendtoaddress(pkh_addr, send_amount)
            number_inputs += 1
        # Now do segwit/legacy multisig
        if multisig:
            if input_type == 'legacy' or input_type == 'all':
                self.wpk_rpc.sendtoaddress(sh_multi_addr, send_amount)
                number_inputs += 1
            if input_type == 'segwit' or input_type == 'all':
                self.wpk_rpc.sendtoaddress(wsh_multi_addr, send_amount)
                self.wpk_rpc.sendtoaddress(sh_wsh_multi_addr, send_amount)
                number_inputs += 2

        self.wpk_rpc.generatetoaddress(6, self.wpk_rpc.getnewaddress())

        # Spend different amounts, requiring 1 to 3 inputs
        for i in range(number_inputs):
            # Create a psbt spending the above
            psbt = self.wrpc.walletcreatefundedpsbt([], [{self.wpk_rpc.getnewaddress():(i+1)*send_amount}], 0, {'includeWatching': True, 'subtractFeeFromOutputs': [0]}, True)
            sign_res = process_commands(self.dev_args + ['signtx', psbt['psbt']])
            finalize_res = self.wrpc.finalizepsbt(sign_res['psbt'])
            self.assertTrue(finalize_res['complete'])
        self.wrpc.sendrawtransaction(finalize_res['hex'])

    # Test wrapper to avoid mixed-inputs signing for Ledger
    def test_signtx(self):
        supports_mixed = {'coldcard', 'trezor'}
        supports_multisig = {'ledger', 'trezor'}
        if self.type not in supports_mixed:
            self._test_signtx("legacy", self.type in supports_multisig)
            self._test_signtx("segwit", self.type in supports_multisig)
        else:
            self._test_signtx("all", self.type in supports_multisig)

class TestDisplayAddress(DeviceTestCase):

    def test_display_address_bad_args(self):
        result = process_commands(self.dev_args + ['displayaddress', '--sh_wpkh', '--wpkh', 'm/49h/1h/0h/0/0'])
        self.assertIn('error', result)
        self.assertIn('code', result)
        self.assertEqual(result['code'], -7)

    def test_display_address(self):
        process_commands(self.dev_args + ['displayaddress', 'm/44h/1h/0h/0/0'])
        process_commands(self.dev_args + ['displayaddress', '--sh_wpkh', 'm/49h/1h/0h/0/0'])
        process_commands(self.dev_args + ['displayaddress', '--wpkh', 'm/84h/1h/0h/0/0'])

class TestSignMessage(DeviceTestCase):

    def test_sign_msg(self):
        process_commands(self.dev_args + ['signmessage', 'Message signing test', 'm/44h/1h/0h/0/0'])
