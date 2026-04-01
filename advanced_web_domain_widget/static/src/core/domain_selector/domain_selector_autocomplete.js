/** @odoo-module **/

import { MultiRecordSelector } from "@advanced_web_domain_widget/core/record_selector/multi_record_selector";
import { _t } from "@web/core/l10n/translation";
import { formatAST, toPyValue } from "@web/core/py_js/py_utils";
import { Expression } from "@advanced_web_domain_widget/core/domain_tree";
import { RecordSelector } from "@advanced_web_domain_widget/core/record_selector/record_selector";

export const isId = (val) => Number.isInteger(val) && val >= 1;

export const getFormat = (val, displayNames, resModel="") => {
    let text;
    let colorIndex;
    if (isId(val) || (['res.users', 'res.company'].includes(resModel) && val==0)) {
        text =
            typeof displayNames[val] === "string"
                ? displayNames[val]
                : _t("Inaccessible/missing record ID: %s", val);
        colorIndex = typeof displayNames[val] === "string" ? 0 : 2; // 0 = grey, 2 = orange
    } else {
        text =
            val instanceof Expression
                ? String(val)
                : _t("Invalid record ID: %s", formatAST(toPyValue(val)));
        colorIndex = val instanceof Expression ? 2 : 1; // 1 = red
    }
    return { text, colorIndex };
};

export class DomainSelectorAutocomplete extends MultiRecordSelector {
    static props = {
        ...MultiRecordSelector.props,
        resModel: {type: String, optional: true},
        resIds: true, //resIds could be an array of ids or an array of expressions
    };

    getIds(props = this.props) {
        return props.resIds.filter((val) => isId(val));
    }

    getTags(props, displayNames) {
        return props.resIds.map((val, index) => {
            if(['res.users', 'res.company'].includes(this.props.resModel) && val==0) {
                displayNames[val] = this.props.resModel == 'res.users'? "Enviornment user": "Enviornment Company";
            }
            const { text, colorIndex } = getFormat(val, displayNames, this.props.resModel);
            return {
                text,
                colorIndex,
                onDelete: () => {
                    this.props.update([
                        ...this.props.resIds.slice(0, index),
                        ...this.props.resIds.slice(index + 1),
                    ]);
                },
            };
        });
    }
}

export class DomainSelectorSingleAutocomplete extends RecordSelector {
    static props = {
        ...RecordSelector.props,
        resId: true,
    };

    getDisplayName(props = this.props, displayNames) {
        const { resId } = props;
        if (resId === false) {
            return "";
        }
        if(['res.users', 'res.company'].includes(this.props.resModel) && resId==0) {
            displayNames[resId] = this.props.resModel == 'res.users'? "Environment user": "Environment Company";
        }
        const { text } = getFormat(resId, displayNames, this.props.resModel);
        return text;
    }

    getIds(props = this.props) {
        if (isId(props.resId)) {
            return [props.resId];
        }
        return [];
    }
}
