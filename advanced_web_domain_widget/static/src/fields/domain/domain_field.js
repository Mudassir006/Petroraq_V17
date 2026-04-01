/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import {
  Domain,
  InvalidDomainError,
} from "@advanced_web_domain_widget/core/domain";
import { DomainSelector } from "@advanced_web_domain_widget/core/domain_selector/domain_selector";
import { DomainSelectorDialog } from "@advanced_web_domain_widget/core/domain_selector_dialog/domain_selector_dialog";
import { EvaluationError } from "@web/core/py_js/py_interpreter";
import { registry } from "@web/core/registry";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useBus, useService, useOwnedDialogs } from "@web/core/utils/hooks";
import { toTree } from "@advanced_web_domain_widget/core/domain_tree";
import {
  useGetDomainTreeDescription,
  useGetDefaultLeafDomain,
} from "@advanced_web_domain_widget/core/domain_selector/utils";

function calculateDate(domain) {
  if (Array.isArray(domain)) {
    const field_name = domain[0];
    const operator = domain[1];
    const val = domain[2];

    const current_date = new Date();
    current_date.setHours(0, 0, 0, 0);

    if (operator !== "date_filter") {
        return [domain];
    }

    if (val === "today") {
        const start_of_today = new Date(current_date);
        const end_of_today = new Date(current_date);
        end_of_today.setDate(end_of_today.getDate() + 1);

        return ["&", [field_name, ">=", start_of_today], [field_name, "<", end_of_today]];
    }

    if (val === "this_week") {
        const start_of_week = new Date(current_date);
        start_of_week.setDate(current_date.getDate() - current_date.getDay());
        const end_of_week = new Date(start_of_week);
        end_of_week.setDate(end_of_week.getDate() + 7);

        return ["&", [field_name, ">=", start_of_week], [field_name, "<", end_of_week]];
    }

    if (val === "this_month") {
        const start_of_month = new Date(current_date);
        start_of_month.setDate(1);
        const end_of_month = new Date(current_date);
        end_of_month.setMonth(end_of_month.getMonth() + 1, 0);

        return ["&", [field_name, ">=", start_of_month], [field_name, "<=", end_of_month]];
    }

    if (val === "this_quarter") {
        const start_of_quarter = new Date(current_date);
        start_of_quarter.setMonth(Math.floor(start_of_quarter.getMonth() / 3) * 3, 1);
        const end_of_quarter = new Date(start_of_quarter);
        end_of_quarter.setMonth(end_of_quarter.getMonth() + 3, 0);

        return ["&", [field_name, ">=", start_of_quarter], [field_name, "<", end_of_quarter]];
    }

    if (val === "this_year") {
        const start_of_year = new Date(current_date);
        start_of_year.setMonth(0, 1);
        const end_of_year = new Date(start_of_year);
        end_of_year.setFullYear(end_of_year.getFullYear() + 1, 0, 0);

        return ["&", [field_name, ">=", start_of_year], [field_name, "<", end_of_year]];
    }

    if (val === "last_day") {
        const start_of_yesterday = new Date(current_date);
        start_of_yesterday.setDate(start_of_yesterday.getDate() - 1);

        return ["&", [field_name, ">=", start_of_yesterday], [field_name, "<", current_date]];
    }

    if (val === "last_week") {
        const end_of_last_week = new Date(current_date);
        end_of_last_week.setDate(end_of_last_week.getDate() - end_of_last_week.getDay());
        const start_of_last_week = new Date(end_of_last_week);
        start_of_last_week.setDate(start_of_last_week.getDate() - 6);

        return ["&", [field_name, ">=", start_of_last_week], [field_name, "<", end_of_last_week]];
    }

    if (val === "last_month") {
        const start_of_last_month = new Date(current_date);
        start_of_last_month.setMonth(start_of_last_month.getMonth() - 1, 1);
        const end_of_last_month = new Date(start_of_last_month);
        end_of_last_month.setMonth(end_of_last_month.getMonth() + 1, 0);

        return ["&", [field_name, ">=", start_of_last_month], [field_name, "<", end_of_last_month]];
    }

    if (val === "last_quarter") {
        const start_of_this_quarter = new Date(current_date);
        start_of_this_quarter.setMonth(Math.floor(start_of_this_quarter.getMonth() / 3) * 3, 1);
        const end_of_last_quarter = new Date(start_of_this_quarter);
        end_of_last_quarter.setMonth(end_of_last_quarter.getMonth() - 1, 0);
        const start_of_last_quarter = new Date(end_of_last_quarter);
        start_of_last_quarter.setMonth(start_of_last_quarter.getMonth() - 3, 1);

        return ["&", [field_name, ">=", start_of_last_quarter], [field_name, "<", end_of_last_quarter]];
    }

    if (val === "last_year") {
        const end_of_last_year = new Date(current_date);
        end_of_last_year.setFullYear(end_of_last_year.getFullYear() - 1, 0, 0);
        const start_of_last_year = new Date(end_of_last_year);
        start_of_last_year.setFullYear(start_of_last_year.getFullYear() - 1, 0, 1);

        return ["&", [field_name, ">=", start_of_last_year], [field_name, "<", end_of_last_year]];
    }

    if (val === "last_7_days") {
        const start_of_last_7_days = new Date(current_date);
        start_of_last_7_days.setDate(start_of_last_7_days.getDate() - 7);

        return [[field_name, ">=", start_of_last_7_days]];
    }

    if (val === "last_30_days") {
        const start_of_last_30_days = new Date(current_date);
        start_of_last_30_days.setDate(start_of_last_30_days.getDate() - 30);

        return [[field_name, ">=", start_of_last_30_days]];
    }

    if (val === "last_90_days") {
        const start_of_last_90_days = new Date(current_date);
        start_of_last_90_days.setDate(start_of_last_90_days.getDate() - 90);

        return [[field_name, ">=", start_of_last_90_days]];
    }

    if (val === "last_365_days") {
        const start_of_last_365_days = new Date(current_date);
        start_of_last_365_days.setDate(start_of_last_365_days.getDate() - 365);

        return [[field_name, ">=", start_of_last_365_days]];
    }

    if (val === "next_day") {
        const start_of_next_day = new Date(current_date);
        start_of_next_day.setDate(start_of_next_day.getDate() + 1);
        const end_of_next_day = new Date(start_of_next_day);
        end_of_next_day.setDate(end_of_next_day.getDate() + 1);

        return ["&", [field_name, ">=", start_of_next_day], [field_name, "<", end_of_next_day]];
    }

    if (val === "next_week") {
        const start_of_next_week = new Date(current_date);
        start_of_next_week.setDate(current_date.getDate() + (7 - current_date.getDay()));
        const end_of_next_week = new Date(start_of_next_week);
        end_of_next_week.setDate(end_of_next_week.getDate() + 7);

        return ["&", [field_name, ">=", start_of_next_week], [field_name, "<", end_of_next_week]];
    }

    if (val === "next_month") {
      const start_of_next_month = new Date(current_date);
            start_of_next_month.setMonth(current_date.getMonth() + 1, 1);
            const end_of_next_month = new Date(start_of_next_month);
            end_of_next_month.setMonth(end_of_next_month.getMonth() + 1, 1);

            return ["&", [field_name, ">=", start_of_next_month], [field_name, "<", end_of_next_month]];
        }

        if (val === "next_quarter") {
            const start_of_this_quarter = new Date(current_date);
            start_of_this_quarter.setMonth(Math.floor(start_of_this_quarter.getMonth() / 3) * 3, 1);
            const end_of_next_quarter = new Date(start_of_this_quarter);
            end_of_next_quarter.setMonth(end_of_next_quarter.getMonth() + 3, 0);
            const start_of_next_quarter = new Date(end_of_next_quarter);
            start_of_next_quarter.setMonth(start_of_next_quarter.getMonth() + 1, 1);

            return ["&", [field_name, ">=", start_of_next_quarter], [field_name, "<", end_of_next_quarter]];
        }

        if (val === "next_year") {
            const start_of_next_year = new Date(current_date);
            start_of_next_year.setFullYear(current_date.getFullYear() + 1, 0, 1);
            const end_of_next_year = new Date(start_of_next_year);
            end_of_next_year.setFullYear(end_of_next_year.getFullYear() + 1, 0, 0);

            return ["&", [field_name, ">=", start_of_next_year], [field_name, "<", end_of_next_year]];
        }
    }
    return [domain];
}

export class DomainFieldBits extends Component {
  static template = "advanced_web_domain_widget.DomainField";
  static components = {
    DomainSelector,
  };
  static props = {
    ...standardFieldProps,
    context: { type: Object, optional: true },
    editInDialog: { type: Boolean, optional: true },
    resModel: { type: String, optional: true },
    isFoldable: { type: Boolean, optional: true },
  };
  static defaultProps = {
    editInDialog: false,
    isFoldable: false,
  };

  setup() {
    this.rpc = useService("rpc");
    this.orm = useService("orm");
    this.getDomainTreeDescription = useGetDomainTreeDescription();
    this.getDefaultLeafDomain = useGetDefaultLeafDomain();
    this.addDialog = useOwnedDialogs();

    this.state = useState({
      isValid: null,
      recordCount: null,
      folded: this.props.isFoldable,
      facets: [],
    });

    this.isDebugEdited = false;
    onWillStart(() => {
      this.checkProps(); // not awaited
      if (this.props.isFoldable) {
        this.loadFacets();
      }
    });
    onWillUpdateProps((nextProps) => {
      this.isDebugEdited =
        this.isDebugEdited && this.props.readonly === nextProps.readonly;
      if (!this.isDebugEdited) {
        this.checkProps(nextProps); // not awaited
      }
      if (nextProps.isFoldable) {
        this.loadFacets(nextProps);
      }
    });

    useBus(this.props.record.model.bus, "NEED_LOCAL_CHANGES", async (ev) => {
      if (this.isDebugEdited) {
        const props = this.props;
        ev.detail.proms.push(
          this.quickValidityCheck(props).then((isValid) => {
            if (isValid) {
              this.isDebugEdited = false; // will allow the count to be loaded if needed
            } else {
              this.state.isValid = true;
              this.state.recordCount = 0;
              props.record.setInvalidField(props.name);
            }
          })
        );
      }
    });
  }

  getContext(props = this.props) {
    return props.context;
  }

  getDomain(props = this.props) {
    return props.record.data[props.name] || "[]";
  }

  getEvaluatedDomain(props = this.props) {
    const domainStringRepr = this.getDomain(props);
    const evalContext = this.getContext(props);
    try {
      const domain = new Domain(domainStringRepr).toList(evalContext);
      // Here, there is still some incertitude on the domain validity.
      // we could improve this check but a complete (async) check is done
      // when loading the record count associated with the domain.
      return domain;
    } catch (error) {
      if (
        error instanceof InvalidDomainError ||
        error instanceof EvaluationError
      ) {
        return { isInvalid: true };
      }
      throw error;
    }
  }

  getResModel(props = this.props) {
    let resModel = props.resModel;
    if (props.record.fieldNames.includes(resModel)) {
      resModel = props.record.data[resModel];
    }
    return resModel;
  }

  async addCondition() {
    const defaultDomain = await this.getDefaultLeafDomain(this.getResModel());
    this.update(defaultDomain);
    this.state.folded = false;
  }

  async loadFacets(props = this.props) {
    const resModel = this.getResModel(props);

    if (!resModel) {
      this.state.facets = [];
      this.state.folded = false;
      return;
    }

    if (typeof resModel !== "string") {
      // we don't want to support invalid models
      throw new Error(`Invalid model: ${resModel}`);
    }

    let promises;
    const domain = this.getDomain(props);
    try {
      const tree = toTree(domain, { distributeNot: !this.env.debug });
      const trees = !tree.negate && tree.value === "&" ? tree.children : [tree];
      promises = trees.map(async (tree) => {
        const description = await this.getDomainTreeDescription(resModel, tree);
        return description;
      });
    } catch (error) {
      if (
        error.data?.name === "builtins.KeyError" &&
        error.data.message === resModel
      ) {
        // we don't want to support invalid models
        throw new Error(`Invalid model: ${resModel}`);
      }
      this.state.facets = [];
      this.state.folded = false;
    }
    this.state.facets = await Promise.all(promises);
  }

  async checkProps(props = this.props) {
    const resModel = this.getResModel(props);
    if (!resModel) {
      this.updateState({});
      return;
    }

    if (typeof resModel !== "string") {
      // we don't want to support invalid models
      throw new Error(`Invalid model: ${resModel}`);
    }

    const domain = this.getEvaluatedDomain(props);
    if (domain.isInvalid) {
      this.updateState({ isValid: false, recordCount: 0 });
      return;
    }

    let recordCount;
    const context = this.getContext(props);
    try {
      const newDomain = [];
      domain.forEach((ele) => {
          if(ele.includes("date_filter") && !isNaN(new Date(ele[2]))) {
            ele[2] = "today";
          }
          if(ele.includes("date_filter")) {
              calculateDate(ele).forEach(el => newDomain.push(el));
          } else {
              newDomain.push(ele);
          }
      });
      recordCount = await this.orm.silent.searchCount(resModel, newDomain, {
        context,
      });
    } catch (error) {
      if (
        error.data?.name === "builtins.KeyError" &&
        error.data.message === resModel
      ) {
        // we don't want to support invalid models
        throw new Error(`Invalid model: ${resModel}`);
      }
      this.updateState({ isValid: false, recordCount: 0 });
      return;
    }
    this.updateState({ isValid: true, recordCount });
  }

  onButtonClick() {
    // resModel, domain, and context are assumed to be valid here.
    const domain = this.getEvaluatedDomain();
    const newDomain = [];
      domain.forEach((ele) => {
          if(ele.includes("date_filter") && !isNaN(new Date(ele[2]))) {
            ele[2] = "today";
          }
          if(ele.includes("date_filter")) {
              calculateDate(ele).forEach(el => newDomain.push(el));
          } else {
              newDomain.push(ele);
          }
      });
    this.addDialog(
      SelectCreateDialog,
      {
        title: _t("Selected records"),
        noCreate: true,
        multiSelect: false,
        resModel: this.getResModel(),
        domain: newDomain,
        context: this.getContext(),
      },
      {
        // The counter is reloaded "on close" because some modal allows
        // to modify data that can impact the counter
        onClose: () => this.checkProps(),
      }
    );
  }

  onEditDialogBtnClick() {
    // resModel is assumed to be valid here
    this.addDialog(DomainSelectorDialog, {
      resModel: this.getResModel(),
      domain: this.getDomain(),
      isDebugMode: !!this.env.debug,
      onConfirm: this.update.bind(this),
    });
  }

  async quickValidityCheck(props) {
    const resModel = this.getResModel(props);
    if (!resModel) {
      return false;
    }
    const domain = this.getEvaluatedDomain(props);
    if (domain.isInvalid) {
      return false;
    }
    const newDomain = [];
      domain.forEach((ele) => {
          if(ele.includes("date_filter") && !isNaN(new Date(ele[2]))) {
            ele[2] = "today";
          }
          if(ele.includes("date_filter")) {
              calculateDate(ele).forEach(el => newDomain.push(el));
          } else {
              newDomain.push(ele);
          }
      });
    return this.rpc("/web/domain/validate", { model: resModel, newDomain });
  }

  update(domain, isDebugEdited = false) {
    this.isDebugEdited = isDebugEdited;
    return this.props.record.update({ [this.props.name]: domain });
  }

  fold() {
    this.state.folded = true;
  }

  updateState(params = {}) {
    Object.assign(this.state, {
      isValid: "isValid" in params ? params.isValid : null,
      recordCount: "recordCount" in params ? params.recordCount : null,
    });
  }
}

export const domainFieldBits = {
  component: DomainFieldBits,
  displayName: _t("Domain"),
  supportedOptions: [
    {
      label: _t("Edit in dialog"),
      name: "in_dialog",
      type: "boolean",
    },
    {
      label: _t("Foldable"),
      name: "foldable",
      type: "boolean",
      help: _t("Display the domain using facets"),
    },
    {
      label: _t("Model"),
      name: "model",
      type: "string",
    },
  ],
  supportedTypes: ["char"],
  isEmpty: () => false,
  extractProps({ options }, dynamicInfo) {
    return {
      editInDialog: options.in_dialog,
      isFoldable: options.foldable,
      resModel: options.model,
      context: dynamicInfo.context,
    };
  },
};

registry.category("fields").add("terabits_domain", domainFieldBits);
