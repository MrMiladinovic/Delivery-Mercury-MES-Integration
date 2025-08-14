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

        # --- Map Country ---
        mes_country_id = self._map_odoo_country_to_mes(country_id)
        if not mes_country_id:
             raise UserError(_("Could not map Odoo country '%s' to MES country ID.") % (country_id.name if country_id else 'Unknown'))

        mes_state_id_or_name = ""
        mes_city_id_or_name = ""

        if mes_country_id == 3: # Zambia
            # --- Map State and City for Zambia ---
            mes_state_id_or_name = self._map_odoo_state_to_mes_id(state_id)
            if not mes_state_id_or_name:
                 _logger.warning(f"Could not map Odoo state '{state_id.name if state_id else 'None'}' to MES state ID for Zambia. Using empty string.")
                 # API might handle empty state ID or you might need a default

            mes_city_id_or_name = self._map_odoo_city_to_mes_id(city) # Assuming you map city name to ID
            if not mes_city_id_or_name:
                 _logger.warning(f"Could not map Odoo city '{city}' to MES city ID for Zambia. Using empty string.")
                 # API might handle empty city ID or you might need a default

        else:
            # --- Use Names for Non-Zambia ---
            # For non-Zambia, use names for state and city as per API doc examples.
            # Note: The API doc example for getfreight shows destination_city as "Lusaka" for South Africa (ID 142),
            # which seems like a mistake, but the principle is likely state/city names for non-Zambia.
            # Let's stick to names for non-Zambia.
            mes_state_id_or_name = state_id.name if state_id else ""
            mes_city_id_or_name = city if city else ""

        return mes_country_id, mes_state_id_or_name, mes_city_id_or_name

    def _map_odoo_country_to_mes(self, country_record):
        """ Map Odoo country to MES country ID. """
        # This is a critical part. You need a reliable mapping.
        # Example (you need to build this mapping based on MES Country List):
        # Ensure IDs match the MES API Country List table.
        if not country_record:
            return None
        # Use XML IDs for more robust mapping if available
        try:
            xmlid_data = self.env['ir.model.data']._xmlid_lookup(country_record)
            if xmlid_data:
                xml_id_name = xmlid_data[1] # Get the actual XML ID string
                xml_mapping = {
                    'base.zm': 3,
                    'base.za': 142, # South Africa- Johannesburg
                    'base.in': 8,
                    'base.jp': 9,
                    'base.cn': 10,
                    # Add more mappings based on Odoo's base module XML IDs
                    # You can find these by looking at the base module's data files
                    # or by inspecting ir.model.data records.
                }
                mes_id = xml_mapping.get(xml_id_name)
                if mes_id:
                    return mes_id
        except Exception:
             pass # Fallback to name matching if XML ID lookup fails

        # Fallback to name matching (less robust)
        mapping = {
            'Zambia': 3,
            'Ghana': 6,
            'India': 8,
            'Japan': 9,
            'China': 10,
            # Add more mappings based on the Country List table in the API doc (p. 17)
            'South Africa': 142, # Assuming 'South Africa- Johannesburg' is the primary mapping
            'South Africa- Johannesburg': 142, # Explicit mapping if needed
            'South Africa- Others': 143,
            'United Kingdom': 169, # Assuming 'United Kingdom- London' is primary
            'United Kingdom- London': 169,
            'United Kingdom Others': 170,
            'United States': 171,
            # ... Add more mappings ...
        }
        # Try direct name match first
        mes_id = mapping.get(country_record.name)
        if mes_id:
            return mes_id

        # If no mapping found, return None to indicate error
        _logger.warning(f"No MES country ID found for Odoo country: {country_record.name} (ID: {country_record.id})")
        return None # Or raise an error

    def _map_odoo_state_to_mes_id(self, state_record):
        """ Map Odoo state (for Zambia) to MES state ID. """
         # Example (you need to build this mapping based on MES State List):
         # This is highly dependent on how you store MES IDs.
         # You might store MES ID as a field on res.country.state
         # Or use a mapping dictionary like country.
         # Placeholder:
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
             # ... Add others from State List table (p. 22) ...
         }
        mes_id = zm_state_map.get(state_record.name)
        return str(mes_id) if mes_id else "" # Return as string

    def _map_odoo_city_to_mes_id(self, city_name):
        """ Map Odoo city (for Zambia) to MES city ID. """
        # Similar to state, you need a mapping.
        # Placeholder:
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
            # ... Add others from City List table (p. 23) ...
        }
        mes_id = zm_city_map.get(city_name)
        return str(mes_id) if mes_id else "" # Return as string


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
        # Important: Ensure weight is > 0
        # --- FIX: Use move_ids instead of move_lines ---
        weight = order.shipping_weight or sum([(line.product_id.weight * line.product_uom_qty) for line in order.order_line if line.product_id.weight]) or 0.5
        # Ensure weight is positive
        if weight <= 0:
            weight = 0.5 # Set a minimum weight if calculation fails
            _logger.info(f"Calculated or configured weight for order {order.name} was <= 0. Using default weight: {weight} kg.")

        # Volume/Dimensions are often approximated or taken from packaging
        # Simplified: Assume a box size for now. Improve logic as needed.
        # Important: Ensure dimensions are > 0
        length = max(0.1, 30.0) # Ensure minimum length
        width = max(0.1, 20.0)  # Ensure minimum width
        height = max(0.1, 15.0) # Ensure minimum height
        pieces = max(1, int(sum(line.product_uom_qty for line in order.order_line))) # Ensure at least 1 piece
        declared_value = max(0.01, order.amount_total) # Ensure declared value is positive

        # --- Construct Shipment Data ---
        # Key fix: Ensure source_city and destination_city are correctly formatted
        # For Zambia (Country ID 3): Use City ID (stringified number)
        # For Other Countries: Use City Name (string)
        shipment_data = [{
            "id": "1", # Can be static for calculation
            "vendor_id": "0", # Assuming single store as per API doc example
            "source_country": str(orig_country_id),
            # source_city: ID for Zambia, Name for others
            "source_city": str(orig_city) if orig_country_id == 3 else str(orig_city),
            "destination_country": str(dest_country_id),
            # destination_city: ID for Zambia, Name for others
            "destination_city": str(dest_city) if dest_country_id == 3 else str(dest_city),
            "insurance": 0, # Simplified, make configurable if needed
            "pieces": pieces,
            "length": round(length, 2),
            "width": round(width, 2),
            "height": round(height, 2),
            "gross_weight": round(weight, 2),
            "declared_value": round(declared_value, 2)
        }]

        # --- Prepare API Parameters ---
        # Important Fix: As per the API doc example (p. 6), BOTH domestic_service AND international_service parameters are sent.
        # The API likely determines which one to use based on the shipment data.
        params = {
            'email': email,
            'private_key': private_key,
            # Send BOTH service IDs as per API example (p. 6)
            'domestic_service': carrier.mercury_mes_default_domestic_service,
            'international_service': carrier.mercury_mes_default_international_service,
            'shipment': json.dumps(shipment_data) # Convert list to JSON string
        }

        url = f"{MES_API_BASE_URL}/getfreight"
        # --- Log for Debugging ---
        _logger.info(f"Mercury MES Get Freight Charge - Request URL: {url}")
        _logger.info(f"Mercury MES Get Freight Charge - Request Params: {params}")
        _logger.info(f"Mercury MES Get Freight Charge - Shipment Data Sent: {shipment_data}")

        try:
            response = requests.get(url, params=params, timeout=30) # Add timeout
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
        # Important: Ensure weight is > 0
        # --- FIX: Use move_ids instead of move_lines and product_uom_qty instead of quantity_done ---
        weight = picking.shipping_weight or sum([(move.product_id.weight * move.product_uom_qty) for move in picking.move_ids if move.product_id.weight]) or 0.5
        if weight <= 0:
            weight = 0.5
            _logger.info(f"Calculated or configured weight for picking {picking.name} was <= 0. Using default weight: {weight} kg.")

        # Simplified dimensions again. Ensure > 0.
        length = max(0.1, 30.0)
        width = max(0.1, 20.0)
        height = max(0.1, 15.0)
        # Piece count: Use total quantity, ensure at least 1
        # --- FIX: Use move_ids instead of move_lines and product_uom_qty instead of quantity_done ---
        pieces = max(1, int(sum(move.product_uom_qty for move in picking.move_ids)))
        # Declared value: Often sum of product values or picking value. Ensure positive.
        # --- FIX: Use move_ids instead of move_lines and product_uom_qty instead of quantity_done ---
        declared_value = max(0.01, sum(move.product_id.lst_price * move.product_uom_qty for move in picking.move_ids)) # Simplified

        # --- Prepare API data structure ---
        token_no = picking.name # Use Odoo picking name as unique token
        # Payment type: Often COD (4) for sales orders, Prepaid (2/3) for internal
        # Simplified: Assume COD for now, make configurable
        payment_type = "4" # COD

        sender_info = {
            "s_first_name": sender.name.split(' ')[0] if sender.name else "",
            "s_last_name": " ".join(sender.name.split(' ')[1:]) if sender.name and len(sender.name.split(' ')) > 1 else "",
            "s_country": str(orig_country_id),
            # s_statelist: ID for Zambia, Name for others
            "s_statelist": str(orig_state) if orig_country_id == 3 else str(orig_state),
            # s_city: ID for Zambia, Name for others
            "s_city": str(orig_city) if orig_country_id == 3 else str(orig_city),
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
            # r_statelist: ID for Zambia, Name for others
            "r_statelist": str(dest_state) if dest_country_id == 3 else str(dest_state),
            # r_city: ID for Zambia, Name for others
            "r_city": str(dest_city) if dest_country_id == 3 else str(dest_city),
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

        # --- Prepare API Parameters for Booking ---
        data_to_send = {
            'email': email,
            'private_key': private_key,
            'token_no': token_no, # Must be unique
            # Send BOTH service IDs as per the API documentation example for bookcollectioninternational (p. 8)
            'domestic_service': carrier.mercury_mes_default_domestic_service,      # e.g., 1
            'international_service': carrier.mercury_mes_default_international_service, # e.g., 4 (Same as getfreight)
            'insurance': "0", # Simplified, make configurable if needed
            'shipment': json.dumps([shipment_data]) # Wrap in list and convert to JSON string as per API example
        }

        url = f"{MES_API_BASE_URL}/bookcollectioninternational"
        # --- Log for Debugging ---
        _logger.info(f"Mercury MES Book Shipment - Request URL: {url}")
        # Avoid logging sensitive data like private_key if possible, but log structure
        logged_data = data_to_send.copy()
        logged_data['private_key'] = '***REDACTED***'
        _logger.info(f"Mercury MES Book Shipment - Request Data (sensitive fields redacted): {logged_data}")
        _logger.info(f"Mercury MES Book Shipment - Shipment Data Sent: {shipment_data}")

        try:
            # Note: API doc shows POST with data in URL params. This is unusual.
            # Standard practice is POST with data in body (form or JSON).
            # Let's try sending as form data first (like params, but via POST body).
            response = requests.post(url, data=data_to_send, timeout=30) # Use 'data' for form-encoded
            response.raise_for_status()
            resp_data = response.json()
            _logger.info(f"Mercury MES Book Shipment - Raw Response: {resp_data}")

            error_code = resp_data.get('error_code')
            if error_code == 508: # Success
                rate = resp_data.get('rate')
                waybills = resp_data.get('waybill', [])
                if waybills:
                    calculated_rate = float(rate) if rate else 0.0
                    _logger.info(f"Mercury MES Book Shipment - Success. Rate: {calculated_rate} ZMW, Waybill(s): {waybills} for Picking {picking.name}")
                    return {'rate': calculated_rate, 'waybills': waybills}
                else:
                    _logger.warning("Mercury MES Book Shipment: Success code 508 but no waybill returned.")
                    raise UserError(_("Mercury MES booking successful but no waybill was returned."))
            elif error_code == 515: # Duplicate Token
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
