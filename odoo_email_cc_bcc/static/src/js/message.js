/** @odoo-module */

import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
    },

    async prepareMessageBody(bodyEl) {
        super.prepareMessageBody(...arguments);
        if (Array.isArray(this.props.message.cc_recipient_ids) && this.props.message.cc_recipient_ids.length > 0) {
            this.props.message.cc_recipient_ids.name = await this.orm.call(
                'mail.message',
                'fetch_partner_name',
                ["", this.props.message.cc_recipient_ids]
            );
        }
        
        if (Array.isArray(this.props.message.bcc_recipient_ids) && this.props.message.bcc_recipient_ids.length > 0) {
            this.props.message.bcc_recipient_ids.name = await this.orm.call(
                'mail.message',
                'fetch_partner_name',
                ["", this.props.message.bcc_recipient_ids]
            );
        }        
    }
});


