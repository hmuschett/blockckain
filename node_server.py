from hashlib import sha256
import json
import time

from flask import Flask, request
import requests


class Bloque:
    def __init__(self, id, transacciones, timestamp, hash_previo, nonce=0):
        self.id = id
        self.transacciones = transacciones
        self.timestamp = timestamp
        self.hash_previo = hash_previo
        self.nonce = nonce

    def calcula_hash(self):
        """
        Devuelve el hash del bloque
        """
        bloque_string = json.dumps(self.__dict__, sort_keys=True) 
        return sha256(bloque_string.encode()).hexdigest()


class Blockchain:
    # Dificultad del algoritmo de PoW
    dificultad = 2

    def __init__(self):
        self.transacciones_sin_confirmar = []
        self.cadena = []

    def crea_bloque_genesis(self):
        """
        Una funcion para generar el bloque genesis
        """
        bloque_genesis = Bloque(0, [], 0, "0") 
        bloque_genesis.hash = bloque_genesis.calcula_hash() 
        self.cadena.append(bloque_genesis)
        

    @property
    def ultimo_bloque(self):
        return self.cadena[-1]

    def aniade_bloque(self, bloque, prueba):
        """
        Una funcion que anade el bloque a la cadena despues de verificarlo.
        """
        hash_previo = self.ultimo_bloque.hash
        if hash_previo != bloque.hash_previo:
             return False
        if not Blockchain.es_valido(bloque, prueba): 
            return False
       
        bloque.hash = prueba 
        self.cadena.append(bloque) 
        return True

    @staticmethod
    def prueba_de_trabajo(bloque):
        """
        Una funcion que prueba diferentes valores de nonce hasta
        obtener un hash que cumpla los requisitos.
        """
        bloque.nonce= 0
        hash_calculado= bloque.calcula_hash()
        while not hash_calculado.startswith('0'* Blockchain.dificultad):
            bloque.nonce+= 1
            hash_calculado= bloque.calcula_hash()
            return hash_calculado

    def aniade_nueva_transaccion(self, transaccion):
        self.transacciones_sin_confirmar.append(transaccion)

    @classmethod
    def es_valido(cls, bloque, hash_bloque):
        """
        Comprueba si el hash de un bloque es valido y cumple
        con los requisitos.
        """
        return (hash_bloque.startswith('0' * Blockchain.dificultad) and
                hash_bloque == bloque.calcula_hash())

    @classmethod
    def comprueba_validez_cadena(cls, cadena):
        resultado = True 
        hash_previo = "0"
        for bloque in cadena:
             hash_bloque = bloque.hash
             delattr(bloque, "hash")
            if not cls.es_valido(bloque, hash_bloque) or hash_previo != bloque.hash_previo:
                resultado = False   
                break
            
            bloque.hash, hash_previo = hash_bloque, hash_bloque 
    
        return resultado

    def minar(self):
        """
        Esta funcion sirve de interfaz para anadir las transacciones 
        pendientes a la cadena de bloques, anadiendolas al bloque 
        y calculando la prueba de trabajo.
        """
        if not self.transacciones_sin_confirmar: 
            return False
        ultimo_bloque = self.ultimo_bloque
        nuevo_bloque = Bloque(id=ultimo_bloque.id + 1,
                                transacciones=self.transacciones_sin_confirmar, 
                                timestamp=time.time(),
                                hash_previo=ultimo_bloque.hash)

        prueba = self.prueba_de_trabajo(nuevo_bloque) 
        self.aniade_bloque(nuevo_bloque, prueba)
        
        self.transacciones_sin_confirmar = [] 
        
        return True


app = Flask(__name__)

# La copia del blockchain del nodo
blockchain = Blockchain()
blockchain.crea_bloque_genesis()

# Las direcciones de otros participantes de la red
peers = set()

# endpoint para enviar una nueva transaccion. Sera usado por nuestra 
# aplicacion para anadir nuevos datos (posts) a la cadena de bloques
@approute('/nueva_transaccion', methods=['POST'])
def nueva_transaccion():
    tx_data = request.get_json() 
    campos_obligatorios = ["autor", "contenido"]

    for campo in campos_obligatorios: 
        if not tx_data.get(campo): 
            return "Datos de transaccion invalidos", 404

    tx_data["timestamp"] = time.time() 
    
    blockchain.aniade_nueva_transaccion(tx_data) 
    
    return "Exito", 201


# endpoint para devolver la copia del nodo de la cadena. 
# Nuestra aplicacion usara este endpoint para consultar 
# todos los mensajes a mostrar.
@approute('/cadena', methods=['GET'])
def obten_cadena():
    datos_cadena = [] 
    for bloque in blockchain.cadena:
        datos_cadena.append(bloque.__dict__)

    return json.dumps({"longitud": len(datos_cadena),
                        "cadena": datos_cadena,
                        "peers": list(peers)})


# endpoint para solicitar al nodo que extraiga las 
# transacciones no confirmadas (si las hay). Lo usaremos 
# para iniciar una orden de minar desde nuestra propia aplicacion.
@approute('/minar', methods=['GET'])
def minar_transacciones_no_confirmadas():
    resultado = blockchain.minar() 
    if not resultado:
        return "No hay transacciones para minar"
    else:
        longitud_cadena = len(blockchain.cadena)
        consenso() 
        if longitud_cadena == len(blockchain.cadena): 
            anunciar_nuevo_bloque(blockchain.ultimo_bloque)
    
    return "Se ha minado el Bloque #{}.".format(blockchain.ultimo_bloque.id)


# endpoint para anadir nuevos peers a la red.
@approute('/registrar_nodo', methods=['POST'])
def registra_nuevos_peers():
    direccion = request.get_json()["direccion"] 
    if not direccion: return "Datos invalidos", 400
    
    # Anadimos el nodo a la lista de pares 
    peers.add(direccion)
    
    # Devuelve la cadena de bloques consensada 
    # al nodo recien registrado para que pueda sincronizarse 
    return obten_cadena()


@approute('/registrarse_con', methods=['POST'])
def registrarse_con_nodo_existente():
    """
    Internamente llama al endpoint `registra_nodo` para 
    registrar el nodo actual con el nodo especificado en 
    la peticion, y sincronizar la cadena de bloques asi 
    como los datos de los peers.
    """
    direccion = request.get_json()["direccion"] 
    if not direccion: 
        return "Datos invalidos", 400

    datos = {"direccion": request.host_url} 
    cabeceras = {'Content-Type': "application/json"}
    
    # Hace una solicitud para registrarse en el nodo 
    # remoto y obtener informacion 
    respuesta = requests.post(direccion + "/registrar_nodo", data=json.dumps(datos), headers=cabeceras)

    if respuesta.status_code == 200: 
        global blockchain 
        global peers 
        # actualiza la cadena y los peers 
        volcado_cadena = respuesta.json()['cadena'] 
        blockchain = crear_cadena_desde_volcado(volcado_cadena)
        peers.update(respuesta.json()['peers']) 
        return "Registrado con exito", 200
    else:
        # si algo sale mal, lo pasamos a la respuesta de la API 
        return respuesta.content, respuesta.status_code


def crear_cadena_desde_volcado(volcado_cadena):
   blockchain_generado = Blockchain() 
   blockchain_generado.crea_bloque_genesis() 
   for idx, datos_bloque in enumerate(volcado_cadena): 
       if idx == 0: 
           continue        # ignoramos el bloque genesis           
        bloque = Bloque(datos_bloque["id"], 
                        datos_bloque["transacciones"], 
                        datos_bloque["timestamp"], 
                        datos_bloque["hash_previo"], 
                        datos_bloque["nonce"])
        prueba = datos_bloque['hash'] 
        aniadido = blockchain_generado.aniade_bloque(bloque, prueba) 
        if not aniadido: 
            raise Exception("La cadena no es consistente!")
    return blockchain_generado


# endpoint para anadir un bloque extraido por otro a la 
# cadena del nodo. El bloque es primero verificado por 
# el nodo y luego se anade a la cadena.
@approute('/aniade_bloque', methods=['POST'])
def verifica_y_aniade_bloque():
   datos_bloque = request.get_json() 
   bloque = Bloque(datos_bloque["id"], 
                    datos_bloque["transacciones"], 
                    datos_bloque["timestamp"], 
                    datos_bloque["hash_previo"], 
                    datos_bloque["nonce"])

    prueba = datos_bloque['hash'] 
    aniadido = blockchain.aniade_bloque(bloque, prueba)
    
    if not aniadido: 
        return "El bloque se descarto por el nodo", 400

    return "Bloque anadido a la cadena", 201


# endpoint para consultar las transacciones no confirmadas
@approute('/pendientes_tx')
def obten_pendientes_tx():
    return json.dumps(blockchain.transacciones_sin_confirmar)


def consenso():
    """
    Nuestro sencillo algoritmo de conseso. Si se encuentra una 
    cadena mas larga y valida, nuestra cadena es reemplazada por ella.
    """
    global blockchain
    
    cadena_mas_larga = None 
    longitud_act = len(blockchain.cadena)

    for node in peers: 
        respuesta = requests.get('{}cadena'.format(node)) 
        longitud = respuesta.json()['longitud'] 
        cadena = respuesta.json()['cadena'] 
        if longitud > longitud_act and blockchain.comprueba_validez_cadena(cadena): 
            longitud_act = longitud 
            cadena_mas_larga = cadena
    
    if cadena_mas_larga: 
        blockchain = cadena_mas_larga 
        return True
    
    return False


def anunciar_nuevo_bloque(bloque):
    """
    Una funcion para anunciar a la red 
    cuando un bloque ha sido minado. Otros bloques 
    pueden simplemente verificar la prueba de trabajo 
    y anadirla a sus respectivas cadenas.
    """
    for peer in peers: 
        url = "{}aniade_bloque".format(peer) 
        cabeceras = {'Content-Type': "application/json"} 
        requests.post(url, 
                        data=json.dumps(bloque.__dict__, sort_keys=True), 
                        headers=cabeceras)

