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
        This is a simplified version. You might want to cache the MES lists or use a mapping table.
        """
        # Simplified: Assume country code or name matches MES country name or you have a mapping
        # For Zambia (ID 3), you need state and city IDs.
        # For other countries, you might use names directly.

        # You would ideally call getcountrystatecity API once and cache the results
        # For prototype, let's assume you have a way to get these IDs or names
        # This part requires careful mapping logic

        # Placeholder logic (needs real implementation)
        country_id = partner.country_id
        state_id = partner.state_id
        city = partner.city

        # Example hardcoded mapping (replace with dynamic logic)
        mes_country_id = self._map_odoo_country_to_mes(country_id)
        mes_state_id_or_name = ""
        mes_city_id_or_name = ""

        if mes_country_id == 3: # Zambia
            mes_state_id_or_name = self._map_odoo_state_to_mes_id(state_id)
            mes_city_id_or_name = self._map_odoo_city_to_mes_id(city) # Assuming you map city name to ID
        else:
            # For non-Zambia, use names
            mes_state_id_or_name = state_id.name if state_id else ""
            mes_city_id_or_name = city if city else ""

        return mes_country_id, mes_state_id_or_name, mes_city_id_or_name

    def _map_odoo_country_to_mes(self, country_record):
        """ Map Odoo country to MES country ID. """
        # This is a critical part. You need a reliable mapping.
        # Example (you need to build this mapping based on MES Country List):
        mapping = {
            self.env.ref('base.zm').id: 3, # Zambia
            self.env.ref('base.za').id: 142, # South Africa example
            self.env.ref('base.in').id: 8, # India
            # ... Add more mappings ...
        }
        return mapping.get(country_record.id, country_record.id) # Fallback to ID might not work

    def _map_odoo_state_to_mes_id(self, state_record):
        """ Map Odoo state (for Zambia) to MES state ID. """
         # Example (you need to build this mapping based on MES State List):
         # This is highly dependent on how you store MES IDs.
         # You might store MES ID as a field on res.country.state
         # Or use a mapping dictionary like country.
         # Placeholder:
         if state_record:
             # Assume you have a field `mes_state_id` on res.country.state
             # return state_record.mes_state_id or state_record.name
             # For prototype, let's assume a simple name match or hardcoded map
             zm_state_map = {
                 'Lusaka Province': 1,
                 'Southern Province': 2,
                 # ... Add others ...
             }
             return zm_state_map.get(state_record.name, "")
         return ""

    def _map_odoo_city_to_mes_id(self, city_name):
        """ Map Odoo city (for Zambia) to MES city ID. """
        # Similar to state, you need a mapping.
        # Placeholder:
        if city_name:
            zm_city_map = {
                'Lusaka': 1,
                'Livingstone': 2,
                'Ndola': 13,
                # ... Add others ...
            }
            return zm_city_map.get(city_name, "")
        return ""


    def get_freight_charge(self, carrier, order):
        """Call the Get Freight Charge API."""
        email, private_key = self._get_credentials(carrier)

        # --- Prepare shipment data ---
        # This assumes you are calculating for the order's shipping address
        # You might need to adapt for stock.picking context in send_shipping
        recipient = order.partner_shipping_id

        # --- Get Address IDs/Names ---
        try:
            dest_country_id, dest_state, dest_city = self._get_country_state_city_ids(recipient)
            # For origin, you need to determine it from your warehouse/company
            warehouse = order.warehouse_id
            origin_partner = warehouse.partner_id # Or company_id.partner_id
            orig_country_id, orig_state, orig_city = self._get_country_state_city_ids(origin_partner)
        except Exception as e:
            _logger.error(f"Error mapping address for freight calculation: {e}")
            raise UserError(_("Error mapping address details for Mercury MES: %s") % str(e))


        # --- Get package/weight details ---
        # This is simplified. You might need to calculate based on order lines or packaging.
        # Often, Odoo uses a 'weight' field on the picking or calculates it.
        # For order, you might sum product weights or use a default package.
        weight = order.shipping_weight or sum([(line.product_id.weight * line.product_uom_qty) for line in order.order_line if line.product_id.weight]) or 0.5
        # Volume/Dimensions are often approximated or taken from packaging
        # Simplified: Assume a box size for now. Improve logic as needed.
        length = 30.0
        width = 20.0
        height = 15.0
        pieces = 1 # Simplified
        declared_value = order.amount_total # Or sum of product values


        shipment_data = [{
            "id": "1", # Can be static for calculation
            "vendor_id": "0", # Assuming single store
            "source_country": str(orig_country_id),
            "source_city": str(orig_city) if orig_country_id == 3 else str(orig_city), # ID for ZM, Name otherwise
            "destination_country": str(dest_country_id),
            "destination_city": str(dest_city) if dest_country_id == 3 else str(dest_city), # ID for ZM, Name otherwise
            "insurance": 0, # Simplified, make configurable
            "pieces": pieces,
            "length": round(length, 2),
            "width": round(width, 2),
            "height": round(height, 2),
            "gross_weight": round(weight, 2),
            "declared_value": round(declared_value, 2)
        }]

        params = {
            'email': email,
            'private_key': private_key,
            'domestic_service': carrier.mercury_mes_default_domestic_service,
            'international_service': carrier.mercury_mes_default_international_service,
            'shipment': json.dumps(shipment_data)
        }

        url = f"{MES_API_BASE_URL}/getfreight"
        _logger.info(f"Mercury MES Get Freight Charge Request: {params}")

        try:
            response = requests.get(url, params=params, timeout=30) # Add timeout
            response.raise_for_status()
            data = response.json()
            _logger.info(f"Mercury MES Get Freight Charge Response: {data}")

            error_code = data.get('error_code')
            if error_code == 508: # Success
                rate = data.get('rate')
                if rate is not None:
                    return float(rate)
                else:
                    _logger.warning("Mercury MES Get Freight Charge: Success code 508 but no rate returned.")
                    return 0.0
            else:
                error_msg = data.get('error_msg', 'Unknown error')
                _logger.error(f"Mercury MES Get Freight Charge failed: {error_msg} (Code: {error_code})")
                raise UserError(_("Mercury MES Get Freight Charge failed: %s (Code: %s)") % (error_msg, error_code))

        except requests.exceptions.RequestException as e:
            _logger.error(f"Mercury MES Get Freight Charge Request failed: {e}")
            raise UserError(_("Mercury MES Get Freight Charge Request failed: Network error or timeout.")) from e
        except json.JSONDecodeError as e:
            _logger.error(f"Mercury MES Get Freight Charge Response JSON decode failed: {e}, Response text: {response.text}")
            raise UserError(_("Mercury MES Get Freight Charge failed: Invalid response format.")) from e
        except Exception as e:
             _logger.error(f"Mercury MES Get Freight Charge unexpected error: {e}")
             raise UserError(_("Mercury MES Get Freight Charge failed: %s") % str(e)) from e


    def book_shipment(self, carrier, picking):
        """Call the Book Collection (International) API."""
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
        # Use picking's computed shipping weight or calculate
        weight = picking.shipping_weight or sum([(move.product_id.weight * move.quantity_done) for move in picking.move_lines if move.product_id.weight]) or 0.5
        # Simplified dimensions again
        length = 30.0
        width = 20.0
        height = 15.0
        pieces = int(sum(move.quantity_done for move in picking.move_lines)) or 1 # Simplified piece count
        # Declared value: Often sum of product values or picking value
        declared_value = sum(move.product_id.lst_price * move.quantity_done for move in picking.move_lines) or 100.0 # Simplified

        # --- Prepare API data structure ---
        token_no = picking.name # Use Odoo picking name as unique token
        # Payment type: Often COD (4) for sales orders, Prepaid (2/3) for internal
        # Simplified: Assume COD for now, make configurable
        payment_type = "4"

        sender_info = {
            "s_first_name": sender.name.split(' ')[0] if sender.name else "",
            "s_last_name": " ".join(sender.name.split(' ')[1:]) if sender.name and len(sender.name.split(' ')) > 1 else "",
            "s_country": str(orig_country_id),
            "s_statelist": str(orig_state) if orig_country_id == 3 else str(orig_state), # ID for ZM, Name otherwise
            "s_city": str(orig_city) if orig_country_id == 3 else str(orig_city),       # ID for ZM, Name otherwise
            "s_add_1": sender.street or "",
            "s_add_2": sender.street2 or "",
            "s_pin": sender.zip or "",
            "s_mobile_no": sender.mobile or sender.phone or "",
            "s_phone_no": sender.phone or sender.mobile or "",
            "s_ext": "", # Often not used
            "s_email": sender.email or ""
        }

        receiver_info = {
            "r_first_name": recipient.name.split(' ')[0] if recipient.name else "",
            "r_last_name": " ".join(recipient.name.split(' ')[1:]) if recipient.name and len(recipient.name.split(' ')) > 1 else "",
            "r_country": str(dest_country_id),
            "r_statelist": str(dest_state) if dest_country_id == 3 else str(dest_state), # ID for ZM, Name otherwise
            "r_city": str(dest_city) if dest_country_id == 3 else str(dest_city),       # ID for ZM, Name otherwise
            "r_add_1": recipient.street or "",
            "r_add_2": recipient.street2 or "",
            "r_pin": recipient.zip or "",
            "r_mobile_no": recipient.mobile or recipient.phone or "",
            "r_phone_no": recipient.phone or recipient.mobile or "",
            "r_ext": "",
            "r_email": recipient.email or ""
        }

        item_details = {
            "pieces": pieces,
            "length": round(length, 2),
            "width": round(width, 2),
            "height": round(height, 2),
            "gross_weight": round(weight, 2),
            "declared_value": round(declared_value, 2),
            "paymenttype": payment_type
        }

        shipment_data = {
            "shipment_pickup_address": [sender_info],
            "shipment_delivery_address": [receiver_info],
            "shipment_details": [{"paymenttype": payment_type}],
            "item_details": [item_details]
        }

        data_to_send = {
            'email': email,
            'private_key': private_key,
            'token_no': token_no,
            'international_service': carrier.mercury_mes_default_international_service,
            'insurance': "0", # Simplified, make configurable
            'shipment': json.dumps([shipment_data]) # Wrap in list as per API example
        }

        url = f"{MES_API_BASE_URL}/bookcollectioninternational"
        _logger.info(f"Mercury MES Book Shipment Request: {data_to_send}") # Log data carefully, avoid logging keys

        try:
            # Note: API doc shows POST with data in URL params. This is unusual.
            # Standard practice is POST with data in body (form or JSON).
            # Let's try sending as form data first (like params, but via POST body).
            response = requests.post(url, data=data_to_send, timeout=30) # Use 'data' for form-encoded
            response.raise_for_status()
            resp_data = response.json()
            _logger.info(f"Mercury MES Book Shipment Response: {resp_data}")

            error_code = resp_data.get('error_code')
            if error_code == 508: # Success
                rate = resp_data.get('rate')
                waybills = resp_data.get('waybill', [])
                if waybills:
                    return {'rate': float(rate) if rate else 0.0, 'waybills': waybills}
                else:
                    _logger.warning("Mercury MES Book Shipment: Success code 508 but no waybill returned.")
                    raise UserError(_("Mercury MES booking successful but no waybill was returned."))
            elif error_code == 515: # Duplicate Token
                 error_msg = resp_data.get('error_msg1', resp_data.get('error_msg', 'Duplicate Token'))
                 _logger.error(f"Mercury MES Book Shipment failed (Duplicate Token): {error_msg} (Code: {error_code})")
                 raise UserError(_("Mercury MES booking failed: %s. Please ensure the Picking Name is unique for MES.") % error_msg)
            else:
                error_msg = resp_data.get('error_msg1', resp_data.get('error_msg', 'Unknown error'))
                _logger.error(f"Mercury MES Book Shipment failed: {error_msg} (Code: {error_code})")
                raise UserError(_("Mercury MES booking failed: %s (Code: %s)") % (error_msg, error_code))

        except requests.exceptions.RequestException as e:
            _logger.error(f"Mercury MES Book Shipment Request failed: {e}")
            raise UserError(_("Mercury MES booking request failed: Network error or timeout.")) from e
        except json.JSONDecodeError as e:
             _logger.error(f"Mercury MES Book Shipment Response JSON decode failed: {e}, Response text: {response.text}")
             raise UserError(_("Mercury MES booking failed: Invalid response format.")) from e
        except Exception as e:
             _logger.error(f"Mercury MES Book Shipment unexpected error: {e}")
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
                return details[0] if details else {} # Return latest status
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
