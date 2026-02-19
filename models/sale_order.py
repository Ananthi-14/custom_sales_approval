from odoo import models, fields
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    approval_state = fields.Selection([
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string="Approval Status")

    is_child_so = fields.Boolean(string="Child SO")
    is_master_so = fields.Boolean(string="Master SO")

    # =====================================================
    # HELPER → Apply Approver Pricelist (NO manual pricing)
    # =====================================================
    def _apply_approver_pricelist(self):

        approver_pricelist = self.env.user.partner_id.property_product_pricelist

        if not approver_pricelist:
            raise UserError("Approver does not have a pricelist configured.")

        for order in self:
            order.write({
                'pricelist_id': approver_pricelist.id
            })

            # 🔥 Let Odoo recompute automatically
            order.order_line._compute_price_unit()

    # ==========================
    # B2C APPROVAL
    # ==========================
    def action_b2c_approve(self):

        self._apply_approver_pricelist()

        self.write({
            'approval_state': 'approved'
        })

        return True

    # ==========================
    # B2B APPROVAL (MERGE + APPROVE)
    # ==========================
    def action_b2b_approve(self):

        if len(self) < 2:
            raise UserError("Please select at least 2 quotations for B2B merge.")

        partners = self.mapped('partner_id')
        if len(partners) > 1:
            raise UserError("All selected quotations must have the same customer.")

        approver_pricelist = self.env.user.partner_id.property_product_pricelist

        if not approver_pricelist:
            raise UserError("Approver does not have a pricelist configured.")

        # ======================================
        # Create Master SO
        # ======================================
        new_order = self.env['sale.order'].create({
            'partner_id': partners[0].id,
            'pricelist_id': approver_pricelist.id,
            'approval_state': 'approved',
            'is_master_so': True,
            'is_child_so': False,
        })

        # ======================================
        # Merge Lines (NO manual pricing)
        # ======================================
        for order in self:

            for line in order.order_line:

                if line.display_type:
                    continue

                matched_line = new_order.order_line.filtered(
                    lambda l: l.product_id.id == line.product_id.id
                )

                if matched_line:
                    matched_line.product_uom_qty += line.product_uom_qty
                else:
                    self.env['sale.order.line'].create({
                        'order_id': new_order.id,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.product_uom_qty,
                        'product_uom_id': line.product_uom_id.id,
                        'name': line.name,
                    })

            # Mark original quotations
            order.write({
                'approval_state': 'approved',
                'is_child_so': True,
                'is_master_so': False,
            })

        # 🔥 Recompute pricing automatically
        new_order.order_line._compute_price_unit()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Merged Sales Order',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': new_order.id,
            'target': 'current',
        }
