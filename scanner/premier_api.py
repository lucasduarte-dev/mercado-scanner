"""
Cliente para la plataforma Premier Mensajeria
Usa Playwright para automatizar el navegador y buscar envíos por QR
"""
import json
import base64
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class PremierMensajeriaAPI:
    URL = "https://premiermensajeria.lightdata.app/"
    USERNAME = "3Dinsumos"
    PASSWORD = "enviosflex10"
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
    
    def _decode_base64_param(self, value):
        """Decodifica parámetro Base64 de URL"""
        try:
            return base64.b64decode(value).decode('utf-8')
        except:
            return None
    
    def _extract_did_from_link(self, link):
        """Extrae 'did' del link público"""
        try:
            # Formato: https://premiermensajeria.lightdata.app/tracking.php?token=152534d54df4s8a67
            # El DID está al inicio del token
            if 'token=' in link:
                token_param = link.split('token=')[1].split('&')[0]
                # Extraer dígitos consecutivos al inicio usando regex
                match = re.search(r'^(\d+)', token_param)
                if match:
                    return match.group(1)
                
                # Fallback: intentar limpiar caracteres no numéricos
                # El DID son los primeros dígitos del token
                did = ''.join(c for c in token_param if c.isdigit())
                if len(did) >= 6:
                    return did[:6]
                return did
            
            # Fallback: formato antiguo con did en base64
            if 'did=' in link:
                did_param = link.split('did=')[1].split('&')[0]
                return self._decode_base64_param(did_param)
        except:
            return None
        return None
    
    def start(self):
        """Inicia el navegador en modo headless"""
        print("[Premier] Iniciando navegador...")
        self.playwright = sync_playwright().start()
        # Cambiar a headless=False para debugging
        self.browser = self.playwright.chromium.launch(headless=False)
        self.page = self.browser.new_page()
        
    def login(self):
        """Login a la plataforma"""
        try:
            print("[Premier] Navegando a login...")
            self.page.goto(self.URL, timeout=30000)
            
            # Esperar campos de login
            print("[Premier] Esperando campos de login...")
            self.page.wait_for_selector('input[type="text"]', timeout=10000)
            
            # Ingresar credenciales
            print("[Premier] Ingresando credenciales...")
            self.page.fill('input[type="text"]', self.USERNAME)
            self.page.press('input[type="text"]', 'Tab')
            self.page.fill('input[type="password"]', self.PASSWORD)
            self.page.press('input[type="password"]', 'Enter')
            
            # Esperar navegación después del login
            print("[Premier] Esperando navegación post-login...")
            self.page.wait_for_timeout(5000)  # Aumentado a 5 segundos
            
            # Debug: Ver qué hay en la página
            print("[Premier] URL actual:", self.page.url)
            
            # Intentar buscar el link de "Envios" o la sección de envíos
            # Si hay menú, clickear en "Envios" o similar
            try:
                # Buscar link con texto "Envios" o "Envíos"
                envios_link = self.page.query_selector('text=/Envios|Envíos/i')
                if envios_link:
                    print("[Premier] Haciendo click en sección Envíos...")
                    envios_link.click()
                    self.page.wait_for_timeout(2000)
            except:
                print("[Premier] No se encontró link de Envios, asumiendo que ya está en la página correcta")
            
            # Esperar a que aparezca al menos una tabla
            print("[Premier] Esperando tabla de envíos...")
            try:
                self.page.wait_for_selector('table', timeout=5000)
                print("[Premier] ✓ Tabla encontrada")
            except:
                print("[Premier] ⚠ No se encontró tabla después de esperar")
            
            return True
        except Exception as e:
            print(f"[Premier ERROR] Login falló: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def find_qr_match(self, qr_data):
        """
        Busca un envío que coincida con el QR escaneado
        qr_data: {"local": 1, "did": "148029", "cliente": 67, "empresa": 265}
        Retorna: {"found": True, "nombre": "...", "apellido": "...", "tipo": "PARTICULAR|CAMBIO", "status": ...}
        """
        result = {"found": False, "nombre": "", "apellido": "", "tipo": "PARTICULAR", "status": "NO VIGENTE", "mensaje": ""}

        try:
            # Accin solcitada: "QUE TOME MAS DE 10 LINKS" y click en opción específica
            # XPath usuario: /html/body/div[1]/div[1]/div/div/div/div[16]/div[1]/div/div/div[5]/div/div[3]/select/option[6]
            print("[Premier] Configurando vista de filas (Opción 6)...")
            try:
                select_xpath = "/html/body/div[1]/div[1]/div/div/div/div[16]/div[1]/div/div/div[5]/div/div[3]/select"
                target_select = self.page.locator(f"xpath={select_xpath}")
                
                if target_select.is_visible():
                    option_value = target_select.evaluate('''
                        (select) => {
                            if (select.options.length >= 6) {
                                return select.options[5].value; 
                            }
                            return null;
                        }
                    ''')
                    
                    if option_value:
                        print(f"[Premier] Seleccionando opción valor: {option_value}")
                        target_select.select_option(option_value)
                        self.page.wait_for_timeout(2000) # Esperar recarga
                    else:
                        print("[Premier] El select no tiene 6 opciones")
                else:
                    print("[Premier] Selector de paginación no encontrado (XPath)")

            except Exception as e:
                print(f"[Premier] Error cambiando límite de registros: {e}")

            # Acción adicional solicitada: Click en elemento específico antes de buscar
            print("[Premier] Navegando página previa a búsqueda...")
            try:
                nav_button_xpath = "/html/body/div[1]/div[1]/div/div/div/div[16]/div[1]/div/div/div[5]/div/div[2]/ul/li[4]/a"
                if self.page.locator(f"xpath={nav_button_xpath}").is_visible():
                    self.page.locator(f"xpath={nav_button_xpath}").click()
                    self.page.wait_for_timeout(2000)
                else:
                    print("[Premier] ! El botón de navegación (li[4]/a) no está visible.")
            except Exception as e:
                print(f"[Premier] Error clickeando elemento navegación: {e}")

            scanned_did = str(qr_data.get("did", ""))
            print(f"[Premier] Buscando DID: {scanned_did}")
            
            # Debug: Intentar diferentes selectores
            tables = self.page.query_selector_all('table')
            print(f"[Premier] Encontradas {len(tables)} tablas en la página")
            
            rows = self.page.query_selector_all('table tbody tr')
            print(f"[Premier] Encontradas {len(rows)} filas con 'table tbody tr'")
            
            if len(rows) == 0:
                rows = self.page.query_selector_all('tr')
                print(f"[Premier] Encontradas {len(rows)} filas con 'tr' genérico")
            
            if len(rows) == 0:
                self.page.screenshot(path="premier_debug.png")
                print(f"[Premier] DEBUGGING - No se encontraron filas.")
                return result
                
            for i, row in enumerate(rows):
                try:
                    # Extraer Nombre del Cliente desde la columna 8
                    row_customer_name = ""
                    try:
                        cells = row.query_selector_all('td')
                        if len(cells) >= 8:
                            row_customer_name = cells[7].inner_text().strip()
                            # print(f"[Premier] Nombre extraído de columna 8: {row_customer_name}")
                    except Exception as col_error:
                        print(f"[Premier] Error extrayendo columna 8: {col_error}")

                    # Click en la fila para abrir el modal
                    row.click()
                    self.page.wait_for_timeout(1500)
                    
                    # Buscar el link público match
                    public_link = None
                    try:
                        link_element = None
                        # Opción A: Input XPath
                        input_xpath = "/html/body/div[1]/div[1]/div/div/div/div[15]/div/div/div[1]/div/div[2]/div/div[2]/div/div[2]/div[1]/input"
                        link_input = self.page.locator(f"xpath={input_xpath}")
                        
                        if link_input.is_visible():
                            public_link = link_input.input_value()
                            if not public_link:
                                self.page.wait_for_timeout(500)
                                public_link = link_input.input_value()
                        else:
                            # Opción B: Input genérico tracking.php
                            input_val = self.page.evaluate('''
                                () => {
                                    const inputs = Array.from(document.querySelectorAll('input'));
                                    const target = inputs.find(i => i.value && i.value.includes('tracking.php'));
                                    return target ? target.value : null;
                                }
                            ''')
                            if input_val:
                                public_link = input_val
                            
                            # Fallback: buscar en <a>
                            if not public_link:
                                link_element = self.page.query_selector('text=Link Publico')
                        
                        # Opción C: Link relativo a texto
                        if not public_link and link_element:
                            parent = link_element.evaluate_handle('el => el.parentElement')
                            links_in_parent = self.page.evaluate('''
                                (parent) => {
                                    const links = parent.querySelectorAll('a');
                                    return Array.from(links).map(a => a.href);
                                }
                            ''', parent)
                            for link in links_in_parent:
                                if 'tracking.php' in link or 'did=' in link:
                                    public_link = link
                                    break
                        
                        # Opción D: Cualquier link en modal
                        if not public_link:
                            links = self.page.eval_on_selector_all('a', 'elements => elements.map(el => el.href)')
                            for link in links:
                                if 'did=' in link or 'tracking.php' in link:
                                    public_link = link
                                    break
                        
                        if public_link:
                            did_from_link = self._extract_did_from_link(public_link)
                            
                            if did_from_link == scanned_did:
                                print(f"[Premier] ✓ Match encontrado! DID: {did_from_link}")
                                result['found'] = True
                                result['status'] = "VIGENTE"
                                
                                # Extraer datos modal
                                try:
                                    page_content = self.page.locator('body').inner_text()
                                    
                                    # TIPO
                                    if 'PARTICULAR' in page_content: result['tipo'] = 'PARTICULAR'
                                    elif 'CAMBIO' in page_content: result['tipo'] = 'CAMBIO'
                                    else:
                                        for line in page_content.split('\n'):
                                            if 'Tracking' in line:
                                                if 'PARTICULAR' in line.upper(): result['tipo'] = 'PARTICULAR'
                                                elif 'CAMBIO' in line.upper(): result['tipo'] = 'CAMBIO'
                                                break
                                    
                                    # NOMBRE
                                    if row_customer_name:
                                        result['nombre'] = row_customer_name
                                    else:
                                        # Fallback modal
                                        lines = page_content.split('\n')
                                        nombre_completo = ""
                                        for j, line in enumerate(lines):
                                            if 'Recibe:' in line:
                                                clean = line.replace('Recibe:', '').strip()
                                                if clean: nombre_completo = clean
                                                elif j+1 < len(lines): nombre_completo = lines[j+1].strip()
                                                break
                                        
                                        if nombre_completo:
                                            result['nombre'] = nombre_completo

                                except Exception as e:
                                    print(f"[Premier] Error extrayendo datos match: {e}")
                                
                                # Cerrar modal y salir
                                self.page.keyboard.press('Escape')
                                self.page.wait_for_timeout(500)
                                return result
                        
                    except Exception as modal_error:
                        print(f"[Premier] Error en modal: {modal_error}")
                    
                    # Cerrar modal si no es match
                    self.page.keyboard.press('Escape')
                    self.page.wait_for_timeout(300)
                    
                except Exception as row_error:
                    print(f"[Premier] Error procesando fila {i}: {row_error}")
                    try:
                        self.page.keyboard.press('Escape')
                        self.page.wait_for_timeout(300)
                    except:
                        pass
            
            print(f"[Premier] No se encontró match para DID: {scanned_did}")
            return result
            
        except Exception as e:
            print(f"[Premier ERROR] Error buscando QR: {e}")
            import traceback
            traceback.print_exc()
            return result

    def fetch_all_shipments(self):
        """
        Scrape masivo: recorre TODAS las filas de la tabla de Premier
        y extrae DID, tipo (PARTICULAR/CAMBIO), y nombre del cliente.
        Retorna lista de dicts: [{"did": "...", "customer_name": "...", "tipo": "...", "raw": {...}}, ...]
        """
        shipments = []
        
        try:
            # Configurar vista para mostrar máximas filas
            print("[Premier PreFetch] Configurando vista de filas (Opción 6)...")
            try:
                select_xpath = "/html/body/div[1]/div[1]/div/div/div/div[16]/div[1]/div/div/div[5]/div/div[3]/select"
                target_select = self.page.locator(f"xpath={select_xpath}")
                
                if target_select.is_visible():
                    option_value = target_select.evaluate('''
                        (select) => {
                            if (select.options.length >= 6) {
                                return select.options[5].value; 
                            }
                            return null;
                        }
                    ''')
                    
                    if option_value:
                        print(f"[Premier PreFetch] Seleccionando opción valor: {option_value}")
                        target_select.select_option(option_value)
                        self.page.wait_for_timeout(3000)
                    else:
                        print("[Premier PreFetch] El select no tiene 6 opciones")
                else:
                    print("[Premier PreFetch] Selector de paginación no encontrado")
            except Exception as e:
                print(f"[Premier PreFetch] Error cambiando límite de registros: {e}")

            # Navegar a la página correcta (li[4])
            print("[Premier PreFetch] Navegando a la página de envíos...")
            try:
                nav_button_xpath = "/html/body/div[1]/div[1]/div/div/div/div[16]/div[1]/div/div/div[5]/div/div[2]/ul/li[4]/a"
                if self.page.locator(f"xpath={nav_button_xpath}").is_visible():
                    self.page.locator(f"xpath={nav_button_xpath}").click()
                    self.page.wait_for_timeout(2000)
                else:
                    print("[Premier PreFetch] Botón de navegación no visible")
            except Exception as e:
                print(f"[Premier PreFetch] Error navegando: {e}")

            # Obtener todas las filas
            rows = self.page.query_selector_all('table tbody tr')
            if len(rows) == 0:
                rows = self.page.query_selector_all('tr')
            
            print(f"[Premier PreFetch] Encontradas {len(rows)} filas para procesar")
            
            for i, row in enumerate(rows):
                try:
                    # Extraer nombre del cliente desde columna 8
                    customer_name = ""
                    try:
                        cells = row.query_selector_all('td')
                        if len(cells) >= 8:
                            customer_name = cells[7].inner_text().strip()
                        if len(cells) == 0:
                            continue  # Skip header rows
                    except:
                        pass

                    # Click en la fila para abrir el modal
                    row.click()
                    self.page.wait_for_timeout(1500)
                    
                    # Extraer link público para obtener DID
                    public_link = None
                    try:
                        input_xpath = "/html/body/div[1]/div[1]/div/div/div/div[15]/div/div/div[1]/div/div[2]/div/div[2]/div/div[2]/div[1]/input"
                        link_input = self.page.locator(f"xpath={input_xpath}")
                        
                        if link_input.is_visible():
                            public_link = link_input.input_value()
                            if not public_link:
                                self.page.wait_for_timeout(500)
                                public_link = link_input.input_value()
                        else:
                            # Fallback: buscar input con tracking.php
                            input_val = self.page.evaluate('''
                                () => {
                                    const inputs = Array.from(document.querySelectorAll('input'));
                                    const target = inputs.find(i => i.value && i.value.includes('tracking.php'));
                                    return target ? target.value : null;
                                }
                            ''')
                            if input_val:
                                public_link = input_val
                            
                            # Fallback: buscar en <a>
                            if not public_link:
                                links = self.page.eval_on_selector_all('a', 'elements => elements.map(el => el.href)')
                                for link in links:
                                    if 'did=' in link or 'tracking.php' in link:
                                        public_link = link
                                        break
                    except Exception as e:
                        print(f"[Premier PreFetch] Error extrayendo link fila {i}: {e}")
                    
                    # Extraer tipo (PARTICULAR/CAMBIO) del contenido del modal
                    tipo = ""
                    try:
                        page_content = self.page.locator('body').inner_text()
                        if 'PARTICULAR' in page_content:
                            tipo = 'PARTICULAR'
                        elif 'CAMBIO' in page_content:
                            tipo = 'CAMBIO'
                    except:
                        pass
                    
                    # Extraer DID del link
                    did = None
                    if public_link:
                        did = self._extract_did_from_link(public_link)
                    
                    # Solo guardar si tiene DID y es PARTICULAR o CAMBIO
                    if did and tipo in ('PARTICULAR', 'CAMBIO'):
                        shipment_data = {
                            'did': did,
                            'customer_name': customer_name,
                            'tipo': tipo,
                            'public_link': public_link,
                            'row_index': i,
                        }
                        shipments.append(shipment_data)
                        print(f"[Premier PreFetch] ✓ Fila {i}: DID={did}, Tipo={tipo}, Cliente={customer_name}")
                    else:
                        print(f"[Premier PreFetch] ✗ Fila {i}: DID={did}, Tipo={tipo or 'N/A'} (saltado)")
                    
                    # Cerrar modal
                    self.page.keyboard.press('Escape')
                    self.page.wait_for_timeout(300)
                    
                except Exception as row_error:
                    print(f"[Premier PreFetch] Error en fila {i}: {row_error}")
                    try:
                        self.page.keyboard.press('Escape')
                        self.page.wait_for_timeout(300)
                    except:
                        pass
            
            print(f"[Premier PreFetch] Completado: {len(shipments)} envíos PARTICULAR/CAMBIO encontrados")
            return shipments
            
        except Exception as e:
            print(f"[Premier PreFetch ERROR] {e}")
            import traceback
            traceback.print_exc()
            return shipments
    
    def close(self):
        """Cierra el navegador"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            print("[Premier] Navegador cerrado")
        except Exception as e:
            print(f"[Premier ERROR] Error cerrando navegador: {e}")


# Función de conveniencia
def buscar_envio_premier(qr_data):
    """
    Busca un envío en Premier Mensajeria
    qr_data: dict con formato {"local": 1, "did": "148029", "cliente": 67, "empresa": 265}
    Retorna: dict con {found, nombre, apellido, tipo}
    """
    api = PremierMensajeriaAPI()
    try:
        api.start()
        if api.login():
            result = api.find_qr_match(qr_data)
            return result
        else:
            return {"found": False, "error": "Login failed"}
    except Exception as e:
        print(f"[Premier ERROR] {e}")
        return {"found": False, "error": str(e)}
    finally:
        api.close()
