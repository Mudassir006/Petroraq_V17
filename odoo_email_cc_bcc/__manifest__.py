# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################
{
  "name"                 :  "ODOO Email CC and BCC",
  "summary"              :  """Enhance the email functionality within Odoo by allowing users to add additional recipients to their emails. Webkul Email CC bcc, Odoo Email cc bcc, Email cc , Email bCC , Webkul mail, Webkul email bcc, Webkul email cc""",
  "category"             :  "Marketing",
  "version"              :  "1.1.0",
  "sequence"             :  1,
  "author"               :  "Webkul Software Pvt. Ltd.",
  "license"              :  "Other proprietary",
  "website"              :  "https://store.webkul.com/Odoo-Email-CC-and-BCC.html",
  "description"          :  """This module extends Odoo's email capabilities by adding support for CC (Carbon Copy) and BCC (Blind Carbon Copy).Easily manage multiple recipients and improve email communication within your organization.""",
  "live_test_url"        :  "http://odoodemo.webkul.com/?module=odoo_email_cc_bcc",
  "depends"              :  ['mail'],
  "data"                 :  [
                             'views/compose_view.xml',
                             'views/mail_message_view.xml',
                            ],
  "assets"               : {
                            'web.assets_backend':[
                              'odoo_email_cc_bcc/static/src/xml/thread.xml',
                              'odoo_email_cc_bcc/static/src/js/message.js',
                             ],
                            },
  "images"               :  ['static/description/Banner.png'],
  "application"          :  True,
  "installable"          :  True,
  "auto_install"         :  False,
  "price"                :  45,
  "currency"             :  "USD",
  "pre_init_hook"        :  "pre_init_check",
}
