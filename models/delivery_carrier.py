# delivery_mercury_mes/models/delivery_carrier.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('mercury_mes', 'Mercury MES')],
        ondelete={'mercury_mes': 'set default'} # Define behavior on carrier deletion
    )

    mercury_mes_email = fields.Char(string="Mercury MES Email", groups='base.group_system')
    mercury_mes_private_key = fields.Char(string="Mercury MES Private Key", groups='base.group.group_system')
    mercury_mes_default_international_service = fields.Integer(string="Default International Service ID", default=5, help="Default service ID for international shipments.")
    mercury_mes_default_domestic_service = fields.Integer(string="Default Domestic Service ID", default=1, help="Default service ID for domestic shipments.")
    # Add fields for prod/test environment if needed
    # mercury_mes_is_test = fields.Boolean(string="Use Test Environment")

    # Override the method to get rate based on the selected delivery type
    def mercury_mes_rate_shipment(self, order):
        """Calculate the rate using Mercury MES API."""
        # This will call the service layer
        service = self.env['mercury.mes.service']
        try:
            rate = service.get_freight_charge(self, order)
            if rate is not None:
                return {
                    'success': True,
                    'price': rate,
                    'error_message': False,
                    'warning_message': False
                }
            else:
                 # Error message should ideally come from the service layer
                return {
                    'success': False,
                    'price': 0.0,
                    'error_message': _("Failed to calculate Mercury MES rate. Please check logs or configuration."),
                    'warning_message': False
                }
        except Exception as e:
            _logger.error(f"Mercury MES Rate Shipment Error: {e}")
            return {
                'success': False,
                'price': 0.0,
                'error_message': str(e),
                'warning_message': False
            }

    # Override the method to send shipment based on the selected delivery type
    def mercury_mes_send_shipping(self, pickings):
        """Book the shipment using Mercury MES API."""
        service = self.env['mercury.mes.service']
        result = []
        for picking in pickings:
            try:
                res = service.book_shipment(self, picking)
                if res:
                    # res should contain 'rate' and 'waybills' (list)
                    # Assuming one waybill per picking for simplicity
                    waybill = res.get('waybills', [None])[0] if res.get('waybills') else None
                    if waybill:
                        # Store the waybill on the picking
                        picking.carrier_tracking_ref = waybill
                        result.append({
                            'exact_price': res.get('rate', 0.0),
                            'tracking_number': waybill
                        })
                    else:
                        raise UserError(_("Mercury MES booking failed, no waybill returned."))
                else:
                     raise UserError(_("Mercury MES booking failed. Please check logs."))
            except Exception as e:
                 _logger.error(f"Mercury MES Send Shipment Error for Picking {picking.name}: {e}")
                 raise UserError(_("Mercury MES booking error: %s") % str(e)) from e
        return result

    # Override the method to cancel shipment (if supported by API)
    def mercury_mes_cancel_shipment(self, picking):
        """Cancel shipment (if API supports it)."""
        # Implement if Mercury MES has a cancel API
        # For now, just log and return a message
        _logger.info(f"Mercury MES Cancel Shipment requested for Picking {picking.name}. API cancellation not implemented.")
        return "Cancel API not implemented for Mercury MES. Please cancel manually in MES."

    # Override the method to get tracking link
    def mercury_mes_get_tracking_link(self, picking):
        """Provide a link to track the shipment."""
        # Construct the tracking URL based on MES documentation or portal
        # Example (replace with actual MES tracking URL if different):
        tracking_ref = picking.carrier_tracking_ref
        if tracking_ref:
            # Assuming tracking is done on the MES server directly
            # You might need to adjust this URL pattern
            return f"http://116.202.29.37/quotation1/app/getshipmenttracking/wbid/{tracking_ref}"
        return False

    # --- Optional: Methods for manual actions ---
    def action_mercury_mes_get_label(self):
        """Action to fetch label (could be implemented later)."""
        # This would involve calling getwaybilldetails and potentially downloading the image
        raise UserError(_("Fetching labels is not yet implemented."))

    def action_mercury_mes_get_tracking_info(self):
        """Action to fetch detailed tracking (could be implemented later)."""
         raise UserError(_("Fetching detailed tracking is not yet implemented."))
