# delivery_mercury_mes/models/delivery_carrier.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('mercury_mes', 'Mercury MES')],
        ondelete={'mercury_mes': 'set default'}
    )

    # Mercury MES Configuration Fields
    mercury_mes_email = fields.Char(
        string="Mercury MES Email",
        groups='base.group_system',
        help="Registered email address for Mercury MES API access."
    )
    mercury_mes_private_key = fields.Char(
        string="Mercury MES Private Key",
        groups='base.group_system',
        help="Private key for Mercury MES API access."
    )
    mercury_mes_default_international_service = fields.Integer(
        string="Default International Service ID",
        default=4,  # Changed from 5 to 4 (matches your working curl)
        help="Default service ID for international shipments."
    )
    mercury_mes_default_domestic_service = fields.Integer(
        string="Default Domestic Service ID",
        default=1,
        help="Default service ID for domestic shipments."
    )
    mercury_mes_insurance = fields.Boolean(
        string="Insurance",
        help="Enable insurance for shipments."
    )

    # --- Odoo Delivery Method Overrides ---

    def mercury_mes_rate_shipment(self, order):
        """Calculate the rate using Mercury MES API."""
        # Validate credentials first
        if not self.mercury_mes_email or not self.mercury_mes_private_key:
            return {
                'success': False,
                'price': 0.0,
                'error_message': _("Mercury MES credentials are not configured."),
                'warning_message': False
            }
            
        service = self.env['mercury.mes.service']
        try:
            rate = service.get_freight_charge(self, order)
            if rate is not None:
                _logger.info(f"Mercury MES Rate Shipment - Calculated Rate: {rate} ZMW for Order {order.name}")
                return {
                    'success': True,
                    'price': float(rate),
                    'error_message': False,
                    'warning_message': False
                }
            else:
                _logger.warning(f"Mercury MES rate_shipment: get_freight_charge returned None for order {order.name}")
                return {
                    'success': False,
                    'price': 0.0,
                    'error_message': _("Failed to calculate Mercury MES rate. Please check logs or configuration."),
                    'warning_message': False
                }
        except UserError as e:
            _logger.error(f"Mercury MES Rate Shipment UserError for Order {order.name}: {e}")
            return {
                'success': False,
                'price': 0.0,
                'error_message': str(e),
                'warning_message': False
            }
        except Exception as e:
            _logger.error(f"Mercury MES Rate Shipment Error for Order {order.name}: {e}", exc_info=True)
            return {
                'success': False,
                'price': 0.0,
                'error_message': _("An unexpected error occurred: %s") % str(e),
                'warning_message': False
            }

    def mercury_mes_send_shipping(self, pickings):
        """Book the shipment using Mercury MES API."""
        # Validate credentials first
        if not self.mercury_mes_email or not self.mercury_mes_private_key:
            raise UserError(_("Mercury MES credentials are not configured."))
            
        service = self.env['mercury.mes.service']
        result = []
        
        for picking in pickings:
            try:
                res = service.book_shipment(self, picking)
                if res:
                    _logger.info(f"Mercury MES Book Shipment Response for Picking {picking.name}: {res}")

                    waybills = res.get('waybills', [])
                    rate = res.get('rate', 0.0)
                    
                    if waybills:
                        waybill = waybills[0]  # Use the first waybill
                        
                        # Store the waybill and rate on the picking
                        picking.carrier_tracking_ref = waybill
                        picking.carrier_price = float(rate)  # FIXED: Use carrier_price instead of delivery_price
                        
                        result.append({
                            'exact_price': float(rate),
                            'tracking_number': waybill
                        })
                        
                        _logger.info(f"Mercury MES Send Shipping - Stored Waybill: {waybill} for Picking {picking.name}")
                        
                        if len(waybills) > 1:
                            _logger.info(f"Mercury MES booking for Picking {picking.name} returned multiple waybills: {waybills}")
                    else:
                        # Handle case where we get rate but no waybill
                        if rate > 0:
                            _logger.warning(f"Mercury MES booking for Picking {picking.name} returned rate {rate} but no waybill")
                            # Still consider successful if we have rate
                            result.append({
                                'exact_price': float(rate),
                                'tracking_number': ''
                            })
                        else:
                            error_msg = _("Mercury MES booking failed, no waybill returned.")
                            _logger.error(error_msg)
                            raise UserError(error_msg)
                else:
                    error_msg = _("Mercury MES booking failed. Please check logs.")
                    _logger.error(error_msg)
                    raise UserError(error_msg)
                    
            except UserError:
                # Re-raise UserError as-is
                raise
            except Exception as e:
                _logger.error(f"Mercury MES Send Shipment Error for Picking {picking.name}: {e}", exc_info=True)
                raise UserError(_("Mercury MES booking error for Picking %s: %s") % (picking.name, str(e))) from e
                    
        return result

    def mercury_mes_cancel_shipment(self, picking):
        """Cancel shipment (if API supports it)."""
        _logger.info(f"Mercury MES Cancel Shipment requested for Picking {picking.name}. API cancellation not implemented.")
        return _("Cancel API not implemented for Mercury MES. Please cancel manually in MES.")

    def mercury_mes_get_tracking_link(self, picking):
        """Provide a link to track the shipment."""
        tracking_ref = picking.carrier_tracking_ref
        if tracking_ref:
            # Updated to use the correct tracking endpoint
            return f"http://116.202.29.37/quotation1/app/getshipmenttracking/wbid/{tracking_ref}"
        return False

    def mercury_mes_get_tracking_info(self, picking):
        """Get detailed tracking information."""
        if not picking.carrier_tracking_ref:
            return []
            
        service = self.env['mercury.mes.service']
        try:
            tracking_details = service.get_tracking_details(picking.carrier_tracking_ref)
            return tracking_details
        except Exception as e:
            _logger.error(f"Error getting tracking info for {picking.carrier_tracking_ref}: {e}")
            return []

    # --- Optional: Methods for manual actions in the UI ---
    def action_mercury_mes_get_label(self):
        """Action to fetch label (could be implemented later)."""
        active_id = self.env.context.get('active_id')
        if active_id:
            picking = self.env['stock.picking'].browse(active_id)
            if picking.carrier_tracking_ref:
                # You could implement label fetching here
                raise UserError(_("Fetching labels is not yet implemented. Tracking number: %s") % picking.carrier_tracking_ref)
            else:
                raise UserError(_("No tracking number found for this shipment."))
        else:
            raise UserError(_("No picking selected."))

    def action_mercury_mes_get_tracking_info(self):
        """Action to fetch detailed tracking (could be implemented later)."""
        active_id = self.env.context.get('active_id')
        if active_id:
            picking = self.env['stock.picking'].browse(active_id)
            if picking.carrier_tracking_ref:
                service = self.env['mercury.mes.service']
                try:
                    tracking_details = service.get_tracking_details(picking.carrier_tracking_ref)
                    if tracking_details:
                        # Format the tracking information for display
                        tracking_info = "\n".join([
                            f"{detail.get('date', '')} - {detail.get('status', '')} - {detail.get('location', '')}"
                            for detail in tracking_details
                        ])
                        raise UserError(_("Tracking Information:\n%s") % tracking_info)
                    else:
                        raise UserError(_("No tracking information found."))
                except Exception as e:
                    raise UserError(_("Error fetching tracking information: %s") % str(e))
            else:
                raise UserError(_("No tracking number found for this shipment."))
        else:
            raise UserError(_("No picking selected."))