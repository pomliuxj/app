import hashlib
import logging
import base64
import json
from Crypto.Cipher import AES
#fat
#key:  sz71c2812e37c3abf666
#securit:  sz71c2812e37c3ab
#test
#key：fghjrty67ertvbnfrgaethvx
#securit:  hsgl91vbns45rtnuwebtyamd

def encrytion(data,type):

    scrt_key= str(data)+'fghjrty67ertvbnfrgaethvx'
    #print(scrt_key)
    try:
       btdata=scrt_key.encode('utf-8')
    except Exception as E:
        logging.info(E)
    if type =='sha1':
        en_sha1=hashlib.new('sha1')
        en_sha1.update(btdata)
        return en_sha1.hexdigest()
    elif type =='md5':
        en_sha1 = hashlib.new('md5')
        en_sha1.update(btdata)
        return en_sha1.hexdigest()
    elif type == 'AES':
        endata=EncryptCBC('hsgl91vbns45rtnuwebtyamd','0102030405060708').encrypt(data)
        return endata

class EncryptCBC:
    def __init__(self,key,iv):
        self.key = key.encode('utf-8') # 初始化密钥
        self.length = AES.block_size  # 初始化数据块大小
        self.iv=iv.encode('utf-8')
        self.aes = AES.new(self.key, AES.MODE_CBC,self.iv)  # 初始化AES,ECB模式的实例
        # 截断函数，去除填充的字符
        self.unpad = lambda date: date[0:-ord(date[-1])]

    def pad(self, text):
        """
        #填充函数，使被加密数据的字节码长度是block_size的整数倍
        """
        count = len(str(text).encode('utf-8'))
        add = self.length - (count % self.length)
        entext = str(text) + (chr(add) * add)
        return entext

    def encrypt(self, encrData):  # 加密函数
        res = self.aes.encrypt(self.pad(encrData).encode("utf8"))
        msg = str(base64.b64encode(res), encoding="utf8")
        return msg

    def decrypt(self, decrData):  # 解密函数
        res = base64.decodebytes(decrData.encode("utf8"))
        msg = self.aes.decrypt(res).decode("utf8")
        return self.unpad(msg)



def paras_join(data,type):
    str_join=[]
    for i in data.keys():
        if i not in ['pid','companyNo','timestamp','nonce','policyNo','customerType','customerLevel','companyName']:
            data[i]=encrytion(data[i],'AES')
    print(json.dumps(data))
    if type==1:
        for j in sorted(list(data.keys())):
            itm = j + '=' + str(data[j])
            str_join.append(itm.replace('+',' '))
        paras = ('&'.join(str_join) + '&' + 'sign' + '=' + encrytion('&'.join(str_join), 'sha1'))
        return paras
    else:
        for j in sorted(list(data.keys())):
            itm = j + '=' + str(data[j])
            str_join.append(itm)
        print('&'.join(str_join))
def paras_gt(data):
    str_join = []
    for j in sorted(list(data.keys())):
        if type(data[j])==dict:
            itm = j + '=' + json.dumps(data[j])
            str_join.append(itm)
        else:
            itm = j + '=' + str(data[j])
            str_join.append(itm)
    print('?' + '&'.join(str_join)+ '&' + 'sign' + '=' + encrytion('&'.join(str_join), 'sha1'))



#saas卡号卡密免登陆
data_distribution={"customerName":"刘先生","customerIdType":"IDENTITY_CARD","customerIdNo":"342623199002185335","customerGender":"MALE","customerBirthDt":"1589817600000","customerMobile":"19900000057","cardNo":"sztest000215","cardPassword":"sztest00006"}

data={"batchCode":"010080","cardInvalidDay":"2020-11-31","cardNo":"sztest000215","cardPwd":"sztest00006","cardValidDay":"2020-08-04","modifyType":"1","nonce":"8985654654128","outActCode":"ACT401203866","outActName":"企业年检-测试卡号卡密有效期","pid":"ertyuji345789qsde56","timestamp":1589789053,"vip":1}

olddata={"nonce":"8985654654128","pid":"ertyuji345789qsde56","timestamp":1589789053,"name":"testliu","certificateType":"2","certificateNo":"sdsaasdas111das","customerMobile":"17349763660","actCode":"ACT131266545","uniqueNo":"test1234512320","staffAccount":"fat1000113","staffPwd":"12345678","outActName":"测试1liuxj","customerLevel":1,"companyName":"测试1liuxjcom","companyNo":"46ss5451ww"}
print(paras_join(data,1))
paras_join(data_distribution,2)

#国泰权益


dataguot={"pid":"gt546456sarewre354","timestamp":"2020052611415122","nonce":"1284982111","cityCode":"110100","gender":"MW","orderNo":"2020060401019945502557","outOrderNo":"autotest1275020432","serviceType":'UW',"providerCode":"543543543543","serviceProductCode":"423432423423"}
dataqueryInstitDos={"pid":"gt546456sarewre354","timestamp":"2020052611415122","nonce":"1284982111","orderNo":"2020060401019945502557","outOrderNo":"autotest1275020432","providerCode":"467987879878","serviceProductCode":'1270fsdfsdfss',"startDate":"2020-06-01","endDate":"2020-08-20","orgCode":"ORG8529674"}
dataplaceOrder={"applyDate":"2020-07-30 11:19:40","appointmentDate":"2020-08-13 00:00:00","channelIdentification":"cathay","endAppointmentDate":"2020-07-23 23:59:59","instSerialNo":"11111231321231","insuranceInfo":{"contactName":"5160BDC0762CCCC81ED64252255E0480","contactTelephone":"3DAD692024428FA419D00D1C73EC217E","customerName":"5160BDC0762CCCC81ED64252255E0480","customerType":"1","customertNo":"6FB191C41BB4DA919A905E31AF3E2FBDDFF9CCCBC7AF7B9FCD9A48BA14AE4146","gender":"M","insuredTelephone":"3DAD692024428FA419D00D1C73EC217E","policyNo":"20200604011610000000000156483001"},"nonce":"4302905136","orderNo":"2020070901013993455145","orgCode":"ORG7532745","outOrderNo":"autotest4302905141","packageCode":"nljdal32920lkbxan","pid":"gt546456sarewre354","providerCode":"SP161123362707","startAppointmentDate":"2020-07-05 00:00:00","timestamp":1591240780}
#{"pid":"gt546456sarewre354","timestamp":"2020052611415845","nonce":"2807496627","orderNo":"2020062201014066580403","outOrderNo":"autotest2807496630","providerCode":"467987879878","orgCode":"ORG7753432","applyDate":"2020-06-08","appointmentDate":"2020-06-13","channelIdentification":"SZP010110040","packageCode":"GDS342648970","instSerialNo":"4sas6d7asd7a","startAppointmentDate":"2020-06-01 15:00:00","endAppointmentDate":"2020-06-20 15:00:00","insuranceInfo":{"policyNo":"454554sadsadasd64d45","gender":"M","contactName":"8EB497D1067D558919D051AC75FE57A4","contactTelephone":"2C8B95CBEDABC152DF8742C63F612F06","customerName":"8EB497D1067D558919D051AC75FE57A4","customerType":"1","customertNo":"BABF070531FEB4F792AC1C60935B2E409C2615D1C6100389A53188331F8EB95F","insuredTelephone":"2C8B95CBEDABC152DF8742C63F612F06"}}
datacnacle={"providerCode":"455645645","pid":"gt546456sarewre354","timestamp":"2020052611415845","nonce":"4292189336","orderNo":"2020070901015328614380","outOrderNo":"autotest4292189340","instSerialNo":"4sas6d7asd7a"}
#paras_join(encjs,1)
#paras_gt(dataplaceOrder)



class encryptECB():
    def __init__(self,key):
        self.length = AES.block_size
        self.key= key

    def pad(self, text):
        """
        #填充函数，使被加密数据的字节码长度是block_size的整数倍
        """
        count = len(str(text).encode('utf-8'))
        add = self.length - (count % self.length)
        entext = str(text) + (chr(add) * add)
        return entext

    def padding_zero(self,value):
        while len(value) % 16 != 0:
            value += '\0'
        return str.encode(value)

    def aes_ecb_encrypt(self,value):
        # AES/ECB/PKCS5padding
        # key is sha1prng encrypted before
        cryptor = AES.new(bytes.fromhex(self.get_sha1prng_key(self.key)), AES.MODE_ECB)
        padding_value = self.pad(value) # padding content with pkcs5
        ciphertext = cryptor.encrypt(padding_value.encode('utf-8'))
        return ''.join(['%02x' % i for i in ciphertext]).upper()
    def get_sha1prng_key(self,key):
        '''[summary]
        encrypt key with SHA1PRNG
        same as java AES crypto key generator SHA1PRNG
        Arguments:
            key {[string]} -- [key]

        Returns:
            [string] -- [hexstring]
        '''
        signature = hashlib.sha1(key.encode()).digest()
        signature = hashlib.sha1(signature).digest()
        return ''.join(['%02x' % i for i in signature]).upper()[:32]


hexstr_content = 'ces'  # content
key = 'hsgl91vbns45rtnuwebtyamd'  # keypassword
aes128string = encryptECB(key).aes_ecb_encrypt(hexstr_content)
print(aes128string)