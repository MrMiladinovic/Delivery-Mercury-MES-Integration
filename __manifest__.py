{
    'name': 'Delivery Mercury MES Integration',
    'summary': 'Integrate Odoo delivery with Mercury MES API',
    'description': """
Integrate Odoo with Mercury MES for shipping cost calculation and shipment booking.
    """,
    'version': '1.0',
    'category': 'Inventory/Delivery',
    'author': 'Marula Tech',
    'depends': ['delivery', 'stock'], # Base modules needed
    'data': [
        'views/delivery_carrier_views.xml',
        # 'data/mercury_mes_data.xml', # Optional
    ],
    'installable': True,
    'application': False, # Set to True if it's a major app
    'auto_install': False,
    'license': 'Other proprietary',
}