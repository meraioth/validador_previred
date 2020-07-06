import re
from datetime import datetime, timedelta
import requests
from requests_toolbelt import MultipartEncoder
import locale
from bs4 import BeautifulSoup
from flask import Flask, request, redirect
import ast

locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')

UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'txt', 'csv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


app = Flask(__name__)


def secrets(key):
    values = {'rut': '11.111.111-1',
              'password': 'password'}
    return values[key]


class PreviredUpload:
    session = None
    default_method_path = 'CtrlFce'
    file_method_path = 'CtrlPdf'
    default_url = 'https://www.previred.com/wPortal/CtrlFce'
    companies_portal_url = 'https://www.previred.com/wEmpresas/CtrlFce'
    upload_portal_url = 'https://www.previred.com/wEmpresas/CtrlUpl'
    login_url = 'https://www.previred.com/wPortal/login/login.jsp'
    companies_regex = re.compile(r'empresa#(\d+)#(\w+)#(true|false)')

    def __init__(self, rut, password, month, mutual_rate, mutual, caja, content):
        self.validate_rut(rut)
        self.session = requests.session()
        self.login(password)
        self.month = month
        self.mutual_rate = mutual_rate
        self.mutual = mutual
        self.content = content
        self.caja = caja

    def validate_rut(self, rut):
        if (rut.find('-') == -1 or rut.find('.') == -1):
            raise Exception('Rut con puntos y guion')
        self.clean_rut_without_dv = rut.split('-')[0].replace('.', '')
        self.rut_dv = rut.split('-')[1]
        self.formated_rut = rut

    def login(self, password):
        self.session.get(self.login_url)
        self.session.headers.update({'Referer': 'https://www.previred.com/wPortal/login/login.jsp',
                                     'Host': 'www.previred.com',
                                     'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:64.0) Gecko/20100101 Firefox/64.0'})
        data_login = {
            'web_rut2': self.formated_rut,
            'web_password': password,
            'reqName': 'prglogin',
            'web_rut': self.clean_rut_without_dv,
            'web_dv': self.rut_dv,
            'web_prg_destino': 'prgroles'
        }
        response = self.session.post(self.default_url, data_login)
        if response.status_code != 200 or len(re.findall('[a-f0-9]{64}', response.text)) == 0:
            raise Exception('Error al ingresar')
        self.token = re.findall('[a-f0-9]{64}', response.text)[0]

    def get_session(self):
        return self.session

    def validate(self):
        self.step_0()
        self.step_1()
        return self.step_5()

    def step_0(self):
        params = {
            'reqName': 'prglogin',
            'web_rut': self.clean_rut_without_dv,
            'web_prg_destino': 'prgloginempresas',
            'is_ipad': 'false',
            'web_rol': 'TE',
            'web_id_context': self.token
        }
        response = self.session.post(self.companies_portal_url, params)
        if len(re.findall(self.companies_regex, response.text)) == 0:
            raise Exception('No existen empresas dónde subir una nómina')

    def step_1(self):
        params = {
            'reqName': 'prgseleccionmodalidad',
            'web_rut': self.clean_rut_without_dv,
            'web_rut_pagador': self.clean_rut_without_dv,
            'web_prg_destino': 'prgloginempresas',
            'is_ipad': 'false',
            'web_rol': 'TE',
            'web_id_context': self.token,
            'web_cod_division': '00',
            'web_periodo': self.month.strftime("%Y%m"),
            'web_accion': 'login'
        }
        response = self.session.post(self.companies_portal_url, params)
        if len(re.findall(self.formated_rut, response.text)) == 0:
            raise Exception('Error')

    def step_5(self):
        params = {
            "reqName": "prgsubenomina",
            "web_rol": "TE",
            "web_periodo": self.month.strftime("%Y%m"),
            "web_rut_pagador": self.clean_rut_without_dv,
            "web_cod_division": "00",
            "web_glosa_tipo_nomina": "Remuneraciones",
            "web_cod_tipo_nomina": '1',
            "web_formato_sel": '1',
            "web_nombre_empresa": "Prueba",
            "webCodMutual": self.mutual,
            "webCodCcaf": self.caja,
            "webTasaMutual": self.mutual_rate,
            "web_tipo_pago": '1',
            "web_archivo_nomina": '1',
            "web_id_context": self.token,
            "web_rut": self.clean_rut_without_dv,
            "web_accion": "login",
            "web_nombre_nomina": "prueba",
            "web_email": "prueba@GMAIL.COM",
            'web_archivo': (
                "nomina.txt", self.content
                , 'text/plain')
        }
        multipart = MultipartEncoder(fields=params)
        print(params)
        response = self.session.post(self.upload_portal_url,
                                     data=multipart,
                                     headers={'Content-Type': multipart.content_type})
        if (response.text.find('ERROR, ARCHIVO INVÁLIDO') != -1 or response.text.find('Errores:') != -1
                or response.text.find('Tipo de Nómina Incorrecto') != -1):
            raise Exception(self.clean_error(response.text))
        return self.clean_success(response.text)

    def clean_error(self, message):
        bs = BeautifulSoup(message)
        table = bs.findAll("table", {"class": "tabla errores"})[0]
        output_rows = []
        for table_row in table.findAll('tr'):
            columns = table_row.findAll('td')
            output_row = []
            for column in columns:
                output_row.append(column.text)
            if len(output_row) > 0:
                output_rows.append(output_row)
        return output_rows

    def clean_success(self, text):
        bs = BeautifulSoup(text)
        table = bs.find('table')
        output_rows = []
        for table_row in table.findAll('tr'):
            columns = table_row.findAll('td')
            output_row = []
            texts = [x.text for x in columns if x.text != '\xa0']
            if any(t.find('$') != -1 for t in texts):
                output_rows.append(texts)
        return output_rows


@app.route('/validate', methods=['POST'])
def validate():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            return "Sin archivo", 500
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            return "Error", 500
        if file and allowed_file(file.filename):
            try:
                previred = PreviredUpload(secrets('rut'), secrets('password'), datetime.strptime('01-06-2020', '%d-%m-%Y'),
                                          request.form['mutual_rate'], request.form['mutual'], request.form['caja'],
                                          file)
                message = previred.validate()
                print(message)
                return {'message': message}
            except Exception as e:
                print(type(e))
                return {'message': ast.literal_eval(str(e))}, 404
    else:
        return 'Not Implemented'


@app.route('/')
def home():
    return 'Validador archivo PREVIRED'


@app.route('/mutuales')
def mutuales():
    return {'ISL': 55,
            'ACHS': 80,
            'MUTUAL': 81,
            'ISL': 82,
            'NA': -1}


@app.route('/cajas')
def cajas():
    return {'NA': -1,
            'ANDES': 61,
            'ARAUCANA': 62,
            'HEROES': 63,
            '18SEPTIEMBRE': 66}


if __name__ == '__main__':
    app.run()
