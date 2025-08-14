# delivery_mercury_mes/models/mercury_mes_service.py

import requests
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MES_API_BASE_URL = "http://116.202.29.37/quotation1/app"

class MercuryMessService(models.AbstractModel):
    _name = 'mercury.mes.service'
    _description = 'Mercury MES API Service'

    def _get_credentials(self, carrier):
        """Retrieve email and private key from the carrier record."""
        email = carrier.mercury_mes_email
        private_key = carrier.mercury_mes_private_key
        if not email or not private_key:
            raise UserError(_("Mercury MES credentials (Email or Private Key) are missing on the delivery method '%s'.") % carrier.name)
        return email, private_key

    def _get_country_state_city_ids(self, partner):
        """Map Odoo partner address to MES IDs/names.
        For Zambia (ID 3): Return Country ID, State ID, City ID.
        For Other Countries: Return Country ID, State Name, City Name.
        """
        # --- Get Address IDs/Names ---
        country_id = partner.country_id
        state_id = partner.state_id
        state_name = state_id.name if state_id else ""
        city_name = partner.city or ""

        mes_country_id = self._map_odoo_country_to_mes(country_id)
        if not mes_country_id:
            raise UserError(_("Could not map Odoo country '%s' to MES country ID.") % (country_id.name if country_id else 'Unknown'))

        mes_state_id_or_name = ""
        mes_city_id_or_name = ""

        if mes_country_id == 3: # Zambia
            # --- Map State and City for Zambia ---
            if state_id:
                mes_state_id_or_name = self._map_odoo_state_to_mes_id(state_id)
            else:
                _logger.warning(f"Odoo Partner {partner.name} (ID: {partner.id}) has no res.country.state record for Zambia.")
                mes_state_id_or_name = "1" # Default to Lusaka

            # Handle city mapping for Zambia
            if not city_name:
                _logger.warning(f"Odoo Partner {partner.name} (ID: {partner.id}) has no city set.")
                mes_city_id_or_name = "1" # Default to Lusaka
            else:
                mes_city_id_or_name = self._map_odoo_city_to_mes_id(city_name)
                if not mes_city_id_or_name:
                    _logger.warning(f"Could not map Odoo city '{city_name}' to MES city ID for Zambia partner {partner.name}.")
                    mes_city_id_or_name = "1" # Default to Lusaka

        else:
            # --- Use Names for Non-Zambia ---
            mes_state_id_or_name = state_name if state_name else ""
            mes_city_id_or_name = city_name if city_name else ""

        return mes_country_id, mes_state_id_or_name, mes_city_id_or_name

    def _map_odoo_country_to_mes(self, country_record):
        """ Map Odoo country to MES country ID. """
        if not country_record:
            return None
        
        # Use XML IDs for more robust mapping if available
        try:
            xmlid_data = self.env['ir.model.data'].search([
                ('model', '=', 'res.country'),
                ('res_id', '=', country_record.id)
            ], limit=1)
            
            if xmlid_data:
                xml_id_name = xmlid_data.name
                xml_mapping = {
                    'zm': 3,
                    'za': 142,
                    'in': 8,
                    'jp': 9,
                    'cn': 10,
                }
                mes_id = xml_mapping.get(xml_id_name)
                if mes_id:
                    return mes_id
        except Exception:
            pass

        # Fallback to name matching
        mapping = {
            'Zambia': 3,
            'Ghana': 6,
            'India': 8,
            'Japan': 9,
            'China': 10,
            'South Africa': 142,
            'South Africa- Johannesburg': 142,
            'South Africa- Others': 143,
            'United Kingdom': 169,
            'United Kingdom- London': 169,
            'United Kingdom Others': 170,
            'United States': 171,
        }
        mes_id = mapping.get(country_record.name)
        if mes_id:
            return mes_id

        _logger.warning(f"No MES country ID found for Odoo country: {country_record.name} (ID: {country_record.id})")
        return None

    def _map_odoo_state_to_mes_id(self, state_record):
        """ Map Odoo state (for Zambia) to MES state ID. """
        if not state_record:
            return ""
        zm_state_map = {
            'Lusaka Province': 1,
            'Southern Province': 2,
            'Copperbelt Province': 3,
            'North Western Province': 4,
            'Northern Province': 5,
            'Western Province': 10,
            'Eastern Province': 11,
            'Luapula Province': 13,
            'Central Province': 14,
            'Muchinga Province': 15,
        }
        mes_id = zm_state_map.get(state_record.name)
        return str(mes_id) if mes_id else "1" # Default to Lusaka

    def _map_odoo_city_to_mes_id(self, city_name):
        """ Map Odoo city (for Zambia) to MES city ID. """
        if not city_name:
            return ""
        zm_city_map = {
            'Lusaka': 1,
            'Livingstone': 2,
            'Ndola': 13,
            'Solwezi': 4,
            'Kitwe': 12,
            'Chingola': 3,
            'Kabwe': 10,
            'Chipata': 19,
            'Mongu': 22,
            'Mansa': 21,
        }
        mes_id = zm_city_map.get(city_name)
        return str(mes_id) if mes_id else "1" # Default to Lusaka

    def sanitize_numbers(self, data):
        """Convert float values to integers where possible to avoid API validation issues"""
        if isinstance(data, dict):
            return {k: self.sanitize_numbers(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_numbers(i) for i in data]
        elif isinstance(data, float) and data.is_integer():
            return int(data)
        else:
            return data

    def get_freight_charge(self, carrier, order):
        """Call the Get Freight Charge API."""
        email, private_key = self._get_credentials(carrier)

        # --- Prepare shipment data ---
        recipient = order.partner_shipping_id

        # --- Get Address IDs/Names ---
        try:
            dest_country_id, dest_state, dest_city = self._get_country_state_city_ids(recipient)
            warehouse = order.warehouse_id
            origin_partner = warehouse.partner_id or order.company_id.partner_id
            orig_country_id, orig_state, orig_city = self._get_country_state_city_ids(origin_partner)
        except Exception as e:
            _logger.error(f"Error mapping address for freight calculation: {e}")
            raise UserError(_("Error mapping address details for Mercury MES: %s") % str(e))

        # --- Get package/weight details ---
        weight = order.shipping_weight or sum([(line.product_id.weight * line.product_uom_qty) for line in order.order_line if line.product_id.weight]) or 0.5
        if weight <= 0:
            weight = 0.5
            _logger.info(f"Calculated or configured weight for order {order.name} was <= 0. Using default weight: {weight} kg.")

        length = max(0.1, 30.0)
        width = max(0.1, 20.0)
        height = max(0.1, 15.0)
        pieces = max(1, int(sum(line.product_uom_qty for line in order.order_line)))
        declared_value = max(0.01, order.amount_total)

        # --- Construct Shipment Data ---
        shipment_data = [{
            "id": "1",
            "vendor_id": "0",
            "source_country": str(orig_country_id),
            "source_city": str(orig_city) if orig_country_id == 3 else str(orig_city),
            "destination_country": str(dest_country_id),
            "destination_city": str(dest_city) if dest_country_id == 3 else str(dest_city),
            "insurance": 0,
            "pieces": pieces,
            "length": round(length, 2),
            "width": round(width, 2),
            "height": round(height, 2),
            "gross_weight": round(weight, 2),
            "declared_value": round(declared_value, 2)
        }]

        # --- Prepare API Parameters ---
        params = {
            'email': email,
            'private_key': private_key,
            'domestic_service': carrier.mercury_mes_default_domestic_service or '1',
            'international_service': carrier.mercury_mes_default_international_service or '4',
            'shipment': json.dumps(shipment_data)
        }

        url = f"{MES_API_BASE_URL}/getfreight"
        _logger.info(f"Mercury MES Get Freight Charge - Request URL: {url}")
        _logger.info(f"Mercury MES Get Freight Charge - Request Params: {params}")
        _logger.info(f"Mercury MES Get Freight Charge - Shipment Data Sent: {shipment_data}")

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            _logger.info(f"Mercury MES Get Freight Charge - Raw Response: {data}")

            error_code = data.get('error_code')
            if error_code == 508: # Success
                rate = data.get('rate')
                if rate is not None:
                    calculated_rate = float(rate)
                    _logger.info(f"Mercury MES Get Freight Charge - Calculated Rate: {calculated_rate} ZMW for Order {order.name}")
                    return calculated_rate
                else:
                    _logger.warning("Mercury MES Get Freight Charge: Success code 508 but no rate returned.")
                    return 0.0
            else:
                error_msg = data.get('error_msg', 'Unknown error')
                _logger.error(f"Mercury MES Get Freight Charge failed: {error_msg} (Code: {error_code}) for Order {order.name}")
                raise UserError(_("Mercury MES Get Freight Charge failed: %s (Code: %s)") % (error_msg, error_code))

        except requests.exceptions.RequestException as e:
            _logger.error(f"Mercury MES Get Freight Charge Request failed for Order {order.name}: {e}")
            raise UserError(_("Mercury MES Get Freight Charge Request failed: Network error or timeout.")) from e
        except json.JSONDecodeError as e:
             _logger.error(f"Mercury MES Get Freight Charge Response JSON decode failed for Order {order.name}: {e}, Response text: {response.text}")
             raise UserError(_("Mercury MES Get Freight Charge failed: Invalid response format.")) from e
        except Exception as e:
             _logger.error(f"Mercury MES Get Freight Charge unexpected error for Order {order.name}: {e}")
             raise UserError(_("Mercury MES Get Freight Charge failed: %s") % str(e)) from e

    def book_shipment(self, carrier, picking):
        """Call the Book Collection API."""
        email, private_key = self._get_credentials(carrier)

        # --- Prepare shipment data ---
        sender = picking.picking_type_id.warehouse_id.partner_id or picking.company_id.partner_id
        recipient = picking.partner_id

        if not sender or not recipient:
            raise UserError(_("Sender or Recipient address is missing on the picking."))

        # --- Get Address IDs/Names ---
        try:
            orig_country_id, orig_state, orig_city = self._get_country_state_city_ids(sender)
            dest_country_id, dest_state, dest_city = self._get_country_state_city_ids(recipient)
        except Exception as e:
            _logger.error(f"Error mapping address for shipment booking: {e}")
            raise UserError(_("Error mapping address details for Mercury MES booking: %s") % str(e))

        # --- Get package/weight details ---
        weight = picking.shipping_weight or sum([(move.product_id.weight * move.product_uom_qty) for move in picking.move_ids if move.product_id.weight]) or 0.5
        if weight <= 0:
            weight = 0.5
            _logger.info(f"Calculated or configured weight for picking {picking.name} was <= 0. Using default weight: {weight} kg.")

        # Calculate dimensions from products
        total_length = total_width = total_height = 0
        total_pieces = 0
        
        for move in picking.move_ids:
            if move.product_id:
                # Convert to integers to avoid float issues
                length = int(round(max(0.1, move.product_id.length or 30.0)))
                width = int(round(max(0.1, move.product_id.width or 20.0)))
                height = int(round(max(0.1, move.product_id.height or 15.0)))
                qty = int(round(max(1, move.product_uom_qty)))
                
                total_length += length * qty
                total_width += width * qty
                total_height += height * qty
                total_pieces += qty

        # Fallback values if no products or calculation fails
        if total_pieces == 0:
            total_pieces = 1
            total_length = 30
            total_width = 20
            total_height = 15

        pieces = max(1, total_pieces)
        length = max(1, int(round(total_length / max(1, pieces))))
        width = max(1, int(round(total_width / max(1, pieces))))
        height = max(1, int(round(total_height / max(1, pieces))))

        # Calculate declared value
        declared_value = max(0.01, sum(move.product_id.lst_price * move.product_uom_qty for move in picking.move_ids if move.product_id))

        # --- Prepare API data structure ---
        token_no = picking.name
        payment_type = "4"  # COD

        sender_info = {
            "s_first_name": sender.name.split(' ')[0] if sender.name else "Unknown",
            "s_last_name": " ".join(sender.name.split(' ')[1:]) if sender.name and len(sender.name.split(' ')) > 1 else "",
            "s_country": str(orig_country_id),
            "s_statelist": str(orig_state) if orig_country_id == 3 else str(orig_state),
            "s_city": str(orig_city) if orig_country_id == 3 else str(orig_city),
            "s_add_1": sender.street or "",
            "s_add_2": sender.street2 or "",
            "s_pin": sender.zip or "",
            "s_mobile_no": (sender.mobile or sender.phone or "").replace('+', '').replace(' ', '')[:15],
            "s_phone_no": (sender.phone or sender.mobile or "").replace('+', '').replace(' ', '')[:15],
            "s_ext": "",
            "s_email": sender.email or ""
        }

        receiver_info = {
            "r_first_name": recipient.name.split(' ')[0] if recipient.name else "Unknown",
            "r_last_name": " ".join(recipient.name.split(' ')[1:]) if recipient.name and len(recipient.name.split(' ')) > 1 else "",
            "r_country": str(dest_country_id),
            "r_statelist": str(dest_state) if dest_country_id == 3 else str(dest_state),
            "r_city": str(dest_city) if dest_country_id == 3 else str(dest_city),
            "r_add_1": recipient.street or "",
            "r_add_2": recipient.street2 or "",
            "r_pin": recipient.zip or "",
            "r_mobile_no": (recipient.mobile or recipient.phone or "").replace('+', '').replace(' ', '')[:15],
            "r_phone_no": (recipient.phone or recipient.mobile or "").replace('+', '').replace(' ', '')[:15],
            "r_ext": "",
            "r_email": recipient.email or ""
        }

        # Sanitize all numeric values to integers
        item_details = {
            "pieces": pieces,
            "length": length,
            "width": width,
            "height": height,
            "gross_weight": int(round(weight)),
            "declared_value": int(round(declared_value)),
            "paymenttype": payment_type
        }

        shipment_data = {
            "shipment_pickup_address": [sender_info],
            "shipment_delivery_address": [receiver_info],
            "shipment_details": [{"paymenttype": payment_type}],
            "item_details": [item_details]
        }

        # Sanitize the entire shipment data
        shipment_data = self.sanitize_numbers(shipment_data)

        # --- Prepare API Parameters for Booking ---
        # KEY FIX 1: Use bookcollection instead of bookcollectioninternational
        data_to_send = {
            'email': email,
            'private_key': private_key,
            'token_no': token_no,
            # KEY FIX 2: Use domestic_service and international_service as per working curl
            'domestic_service': carrier.mercury_mes_default_domestic_service or '1',
            'international_service': carrier.mercury_mes_default_international_service or '4',
            'insurance': "1" if carrier.mercury_mes_insurance else "0",
            'shipment': json.dumps([shipment_data])  # Wrap in list as per working example
        }

        # KEY FIX 3: Use correct endpoint
        url = f"{MES_API_BASE_URL}/bookcollection"
        
        # --- Log for Debugging ---
        _logger.info(f"Mercury MES Book Shipment - Request URL: {url}")
        logged_data = data_to_send.copy()
        logged_data['private_key'] = '***REDACTED***'
        _logger.info(f"Mercury MES Book Shipment - Request Data (sensitive fields redacted): {logged_data}")
        _logger.info(f"Mercury MES Book Shipment - Shipment Data Sent: {shipment_data}")

        try:
            # Use POST with form data
            response = requests.post(url, data=data_to_send, timeout=30)
            response.raise_for_status()
            resp_data = response.json()
            _logger.info(f"Mercury MES Book Shipment - Raw Response: {resp_data}")

            error_code = resp_data.get('error_code')
            # KEY FIX 4: Error code 508 actually means SUCCESS (as per your working test)
            if error_code == 508:  # Success
                rate = resp_data.get('rate')
                waybills = resp_data.get('waybill', [])
                if waybills:
                    calculated_rate = float(rate) if rate else 0.0
                    waybill_number = waybills[0]  # Take first waybill
                    _logger.info(f"Mercury MES Book Shipment - Success. Rate: {calculated_rate} ZMW, Waybill: {waybill_number} for Picking {picking.name}")
                    return {'rate': calculated_rate, 'waybills': [waybill_number]}
                else:
                    _logger.warning("Mercury MES Book Shipment: Success code 508 but no waybill returned.")
                    # Still consider it successful if we get rate
                    if rate is not None:
                        return {'rate': float(rate), 'waybills': []}
                    else:
                        raise UserError(_("Mercury MES booking successful but no waybill was returned."))
            elif error_code == 515:  # Duplicate Token
                 error_msg = resp_data.get('error_msg1', resp_data.get('error_msg', 'Duplicate Token'))
                 _logger.error(f"Mercury MES Book Shipment failed (Duplicate Token) for Picking {picking.name}: {error_msg} (Code: {error_code})")
                 raise UserError(_("Mercury MES booking failed: %s. Please ensure the Picking Name is unique for MES.") % error_msg)
            else:
                error_msg = resp_data.get('error_msg1', resp_data.get('error_msg', 'Unknown error'))
                _logger.error(f"Mercury MES Book Shipment failed for Picking {picking.name}: {error_msg} (Code: {error_code})")
                raise UserError(_("Mercury MES booking failed: %s (Code: %s)") % (error_msg, error_code))

        except requests.exceptions.RequestException as e:
            _logger.error(f"Mercury MES Book Shipment Request failed for Picking {picking.name}: {e}")
            raise UserError(_("Mercury MES booking request failed: Network error or timeout.")) from e
        except json.JSONDecodeError as e:
             _logger.error(f"Mercury MES Book Shipment Response JSON decode failed for Picking {picking.name}: {e}, Response text: {response.text}")
             raise UserError(_("Mercury MES booking failed: Invalid response format.")) from e
        except Exception as e:
             _logger.error(f"Mercury MES Book Shipment unexpected error for Picking {picking.name}: {e}")
             raise UserError(_("Mercury MES booking failed: %s") % str(e)) from e

    # --- Optional methods for tracking, labels, status ---
    def get_tracking_details(self, waybill_number):
        """Get detailed tracking history."""
        url = f"{MES_API_BASE_URL}/getshipmenttrackingdetails/wbid/{waybill_number}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('error_code') == 508:
                return data.get('detail', [])
            else:
                _logger.warning(f"Mercury MES Track Shipment failed for {waybill_number}: {data.get('error_msg')} (Code: {data.get('error_code')})")
                return []
        except Exception as e:
            _logger.error(f"Mercury MES Track Shipment error for {waybill_number}: {e}")
            return []

    def get_current_status(self, waybill_number):
        """Get current shipment status."""
        url = f"{MES_API_BASE_URL}/getshipmenttracking/wbid/{waybill_number}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('error_code') == 508:
                details = data.get('detail', [])
                return details[0] if details else {}
            else:
                 _logger.warning(f"Mercury MES Get Status failed for {waybill_number}: {data.get('error_msg')} (Code: {data.get('error_code')})")
                 return {}
        except Exception as e:
            _logger.error(f"Mercury MES Get Status error for {waybill_number}: {e}")
            return {}

    def get_waybill_details(self, waybill_number):
        """Get waybill details including label URL."""
        url = f"{MES_API_BASE_URL}/getwaybilldetail/bid/{waybill_number}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('error_code') == 508:
                return data.get('detail', {})
            else:
                 _logger.warning(f"Mercury MES Get Waybill Details failed for {waybill_number}: {data.get('error_msg')} (Code: {data.get('error_code')})")
                 return {}
        except Exception as e:
            _logger.error(f"Mercury MES Get Waybill Details error for {waybill_number}: {e}")
            return {}