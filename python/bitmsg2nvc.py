import xmlrpclib
import json
import hashlib
import sys
import os
import shelve
import time
import datetime
from jsonrpclib import jsonrpc
sys.path.append(os.path.dirname(os.path.realpath(sys.argv[0])))
from base58 import b58encode

transactionFee = 0.01
transactionConfirmations = 6
nodeMessageAddress = 'Bitmessage Address'
accountName = 'CryptoWallet Account Name'

class NotInApprovedList(Exception):
    pass

class CryptoClientFault(Exception):
    pass

class CritiacalFault(Exception):
    pass

db=shelve.open("data.db")

bitmessageClient = xmlrpclib.ServerProxy("http://username:password@address:port/")

cryptoClient = jsonrpc.ServerProxy("http://username:password@address:port")

while(True):
    inboxMessages = json.loads(bitmessageClient.getAllInboxMessages())
    transactions = filter(lambda x: (x['category'] == 'receive') and (x['account'] == accountName) and (x['amount'] >= transactionFee) and (x['confirmations'] >= transactionConfirmations), cryptoClient.listtransactions(accountName))
    approvedAddresses = []
    for transaction in transactions:
        trAsm = cryptoClient.gettransaction(transaction['txid'])['vin'][0]['scriptSig']['asm']
        script = trAsm.split()
        h = hashlib.sha256(script[1].decode("hex")).digest()
        ripe160 = hashlib.new('ripemd160')
        ripe160.update(h)
        d = ripe160.digest()
        address = ('\x08' + d)
        checksum = hashlib.sha256(hashlib.sha256(address).digest()).digest()[:4]
        address += checksum
        encoded_address = b58encode(address)

        approvedAddresses.append(encoded_address)

    print str(datetime.datetime.now()) + ": " + 'Approved addresses:'
    print str(datetime.datetime.now()) + ": " + str(approvedAddresses)
    unread = filter(lambda x: (x['read'] < 1) and (x['toAddress'] == nodeMessageAddress), inboxMessages['inboxMessages'])
    for msg in unread:
        decodedMsg = msg['message'].decode('base64')
        text = decodedMsg.split('\n')
        senderCurrencyAddress = text[0]
        command = text[1]
        sign = text[2]
        try:
            if(not(cryptoClient.validateaddress(senderCurrencyAddress))):
                raise ValueError
            if(not(cryptoClient.verifymessage(senderCurrencyAddress, sign, command))):
                raise ValueError
            if(not(senderCurrencyAddress in approvedAddresses)):
                raise NotInApprovedList

            if(command.strip().lower() == 'get address'):
                print str(datetime.datetime.now()) + ": " + "Sending address"
                try:
                    depositAddress = db[senderCurrencyAddress]
                except KeyError:
                    depositAddress = cryptoClient.getnewaddress(senderCurrencyAddress)
                    if(not(cryptoClient.validateaddress(depositAddress))) :
                        raise CryptoClientFault
                    print str(datetime.datetime.now()) + ": " + "New depositAddress:" + depositAddress + " for " + senderCurrencyAddress
                    db[senderCurrencyAddress] = depositAddress
                print str(datetime.datetime.now()) + ": " + "Message sent:" + bitmessageClient.sendMessage(msg['fromAddress'], nodeMessageAddress, "NVCDepo".encode('base64'), depositAddress.encode('base64'));

            if(command.strip().lower() == 'send coins back'):
                print str(datetime.datetime.now()) + ": " + "Sending coins back to" + str(senderCurrencyAddress)
                currentAccountBalance = cryptoClient.getbalance(senderCurrencyAddress, transactionConfirmations)
                print str(datetime.datetime.now()) + ": " + 'Current balance:' + str(currentAccountBalance)
                addressesOfAccount = cryptoClient.getaddressesbyaccount(senderCurrencyAddress)
                unspentTransactions = cryptoClient.listunspent(transactionConfirmations, 9999999, addressesOfAccount)
                depoFees = len(unspentTransactions) * transactionFee
                print str(datetime.datetime.now()) + ": " + 'depoFees: ' + str(depoFees)
                fundsToSend = currentAccountBalance - depoFees
                if((fundsToSend > 0) and (len(unspentTransactions) > 0)):
                    if(len(senderCurrencyAddress) == 0):
                        raise CritiacalFault
                    txId = cryptoClient.sendfrom(senderCurrencyAddress, senderCurrencyAddress, fundsToSend, transactionConfirmations)
                    txInfo = cryptoClient.gettransaction(txId)
                    txFee = reduce(lambda res, x: x['fee'] + res, txInfo['details'], 0)
                    profit = depoFees + txFee
                    cryptoClient.move(senderCurrencyAddress, accountName, profit)
                    print str(datetime.datetime.now()) + ": " + "Fees gained:" + str(profit)
                    print str(datetime.datetime.now()) + ": " + "Message sent:" + bitmessageClient.sendMessage(msg['fromAddress'], nodeMessageAddress, "NVCDepo".encode('base64'), (str(txId) + '\nAmount: ' +str(fundsToSend)).encode('base64'));
                else:
                    print str(datetime.datetime.now()) + ": " + "Message sent:" + bitmessageClient.sendMessage(msg['fromAddress'], nodeMessageAddress, "NVCDepo".encode('base64'), ('Balance: ' +str(fundsToSend)).encode('base64'));

            if(command.strip().lower() == 'get balance'):
                print str(datetime.datetime.now()) + ": " + "Balance request of " + str(senderCurrencyAddress)
                currentAccountBalance = cryptoClient.getbalance(senderCurrencyAddress, transactionConfirmations)
                print str(datetime.datetime.now()) + ": " + 'Current balance:' + str(currentAccountBalance)
                fundsToSend = currentAccountBalance

                print str(datetime.datetime.now()) + ": " + "Message sent:" + bitmessageClient.sendMessage(msg['fromAddress'], nodeMessageAddress, "NVCDepo".encode('base64'), ('Balance: ' +str(fundsToSend)).encode('base64'));
        except ValueError:
            print str(datetime.datetime.now()) + ": " + "FAILED to verify"
            bitmessageClient.getInboxMessageByID(msg['msgid'], True)
        except NotInApprovedList:
            print str(datetime.datetime.now()) + ": " + "NotInApprovedList"
        except CritiacalFault:
            print str(datetime.datetime.now()) + ": " + "CritiacalFault, failed to process " + str(msg['msgid'])
        except:
            print str(datetime.datetime.now()) + ": " + 'InternalError'
        else:
            print str(datetime.datetime.now()) + ": " + "Message processed successfully:" + str(msg['msgid'])
            bitmessageClient.getInboxMessageByID(msg['msgid'], True)
        finally:
            print str(datetime.datetime.now()) + ": " + "FINALLY"
    time.sleep(15)

db.close()
