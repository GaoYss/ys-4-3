<template>
  <div class="split-layout">
    <section class="panel form-panel">
      <h2>{{ editingFee ? '编辑费用标准' : '新增费用标准' }}</h2>
      <form @submit.prevent="saveFeeType" class="form-grid">
        <label>费用名称<input v-model="feeForm.name" required placeholder="物业费" /></label>
        <label>计费方式
          <select v-model="feeForm.billing_method">
            <option value="fixed">固定金额</option>
            <option value="area">按面积</option>
          </select>
        </label>
        <label>金额/单价<input v-model.number="feeForm.amount" type="number" min="0" step="0.01" required /></label>
        <label>周期
          <select v-model="feeForm.cycle">
            <option value="monthly">月度</option>
            <option value="quarterly">季度</option>
            <option value="yearly">年度</option>
          </select>
        </label>
        <label>生效日期<input v-model="feeForm.effective_date" type="date" required /></label>
        <label>说明<textarea v-model="feeForm.description" rows="2"></textarea></label>
        <div class="form-actions">
          <button type="submit">{{ editingFee ? '保存' : '保存标准' }}</button>
          <button v-if="editingFee" type="button" @click="cancelEdit" class="secondary">取消</button>
        </div>
      </form>
      <p v-if="editingFee && editingFee.has_bills" class="notice warn">
        提示：该标准已有账单记录，修改后将自动创建新版本，不影响历史账单
      </p>

      <h2>批量生成账单</h2>
      <form @submit.prevent="generate" class="form-grid">
        <label>费用类型
          <select v-model="generateForm.fee_type" required>
            <option value="" disabled>请选择</option>
            <option v-for="fee in activeFeeTypes" :key="fee.id" :value="fee.id">
              {{ fee.name }} ({{ fee.version_label }})
            </option>
          </select>
        </label>
        <label>账期<input v-model="generateForm.period" required placeholder="2026-06" /></label>
        <label>截止日期<input v-model="generateForm.due_date" type="date" required /></label>
        <button type="submit">生成账单</button>
      </form>
      <p v-if="message" class="notice">{{ message }}</p>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>费用标准</h2>
        <button @click="load">刷新</button>
      </div>

      <div class="fee-groups">
        <div v-for="group in groupedFeeTypes" :key="group.name" class="fee-group">
          <div class="group-active-row" @click="editFee(group.activeRow)">
            <div class="row-col col-name">{{ group.name }}</div>
            <div class="row-col">
              <span class="version-badge">{{ group.activeRow.version_label }}</span>
            </div>
            <div class="row-col">{{ group.activeRow.billing_method_label }}</div>
            <div class="row-col">
              <span v-if="group.activeRow.billing_method === 'area'">¥{{ Number(group.activeRow.amount).toFixed(2) }}/㎡</span>
              <span v-else>¥{{ Number(group.activeRow.amount).toFixed(2) }}</span>
            </div>
            <div class="row-col">{{ group.activeRow.cycle_label }}</div>
            <div class="row-col">
              <span class="status-badge active">启用</span>
            </div>
            <div class="row-col col-actions">
              <button @click.stop="editFee(group.activeRow)" class="link">编辑</button>
              <button v-if="group.oldVersions.length" @click.stop="toggleGroup(group.name)" class="link">
                {{ expandedGroups.has(group.name) ? '收起历史' : `历史版本 (${group.oldVersions.length})` }}
              </button>
            </div>
          </div>

          <div v-if="expandedGroups.has(group.name) && group.oldVersions.length" class="group-old-versions">
            <div v-for="row in group.oldVersions" :key="row.id" class="group-old-row">
              <div class="row-col col-name"></div>
              <div class="row-col">
                <span class="version-badge small">{{ row.version_label }}</span>
              </div>
              <div class="row-col">{{ row.billing_method_label }}</div>
              <div class="row-col">
                <span v-if="row.billing_method === 'area'">¥{{ Number(row.amount).toFixed(2) }}/㎡</span>
                <span v-else>¥{{ Number(row.amount).toFixed(2) }}</span>
              </div>
              <div class="row-col">{{ row.cycle_label }}</div>
              <div class="row-col">
                <span class="status-badge inactive">停用</span>
              </div>
              <div class="row-col col-actions">
                <span class="muted">{{ row.created_at?.split('T')[0] }} 创建</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel-head section-gap">
        <h2>账单列表</h2>
      </div>
      <DataTable :columns="billColumns" :rows="bills">
        <template #cell-status="{ row }"><StatusBadge :status="row.status" /></template>
        <template #cell-amount="{ row }">¥{{ Number(row.amount).toFixed(2) }}</template>
        <template #cell-fee_version_label="{ row }">
          <span class="version-badge small" :title="JSON.stringify(row.fee_type_snapshot, null, 2)">
            {{ row.fee_version_label }}
          </span>
        </template>
      </DataTable>
    </section>

    <div v-if="historyVisible" class="modal-overlay" @click="closeHistory">
      <div class="modal" @click.stop>
        <div class="modal-head">
          <h3>{{ historyFee?.name }} - 版本历史</h3>
          <button @click="closeHistory" class="close">&times;</button>
        </div>
        <div class="modal-body">
          <table class="history-table">
            <thead>
              <tr>
                <th>版本</th>
                <th>生效日期</th>
                <th>计费方式</th>
                <th>金额/单价</th>
                <th>周期</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="h in feeHistory" :key="h.id">
                <td><span class="version-badge">v{{ h.version }}</span></td>
                <td>{{ h.effective_date }}</td>
                <td>{{ h.billing_method_label }}</td>
                <td>
                  <span v-if="h.billing_method === 'area'">¥{{ Number(h.amount).toFixed(2) }}/㎡</span>
                  <span v-else>¥{{ Number(h.amount).toFixed(2) }}</span>
                </td>
                <td>{{ h.cycle_label }}</td>
                <td>
                  <span :class="['status-badge', h.is_active ? 'active' : 'inactive']">
                    {{ h.is_active ? '启用' : '停用' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { propertyApi } from "../api/property";
import DataTable from "../components/DataTable.vue";
import StatusBadge from "../components/StatusBadge.vue";

const feeTypes = ref([]);
const feeHistory = ref([]);
const bills = ref([]);
const message = ref("");
const editingFee = ref(null);
const historyFee = ref(null);
const historyVisible = ref(false);
const expandedGroups = ref(new Set());
const feeForm = reactive({
  name: "",
  billing_method: "fixed",
  amount: 0,
  cycle: "monthly",
  effective_date: "",
  description: ""
});
const generateForm = reactive({ fee_type: "", period: "", due_date: "" });

const activeFeeTypes = computed(() => {
  const latestByFee = new Map();
  feeTypes.value
    .filter(f => f.is_active)
    .sort((a, b) => b.version - a.version)
    .forEach(f => {
      if (!latestByFee.has(f.name)) {
        latestByFee.set(f.name, f);
      }
    });
  return Array.from(latestByFee.values()).sort((a, b) => a.name.localeCompare(b.name));
});

const groupedFeeTypes = computed(() => {
  const groups = new Map();
  feeTypes.value.forEach(f => {
    if (!groups.has(f.name)) {
      groups.set(f.name, { name: f.name, activeRow: null, oldVersions: [] });
    }
    const g = groups.get(f.name);
    if (f.is_active) {
      if (!g.activeRow || f.version > g.activeRow.version) {
        if (g.activeRow) g.oldVersions.unshift(g.activeRow);
        g.activeRow = f;
      } else {
        g.oldVersions.unshift(f);
      }
    } else {
      g.oldVersions.push(f);
    }
  });
  const result = Array.from(groups.values());
  result.forEach(g => {
    g.oldVersions.sort((a, b) => (b.effective_date || "").localeCompare(a.effective_date || "") || b.version - a.version);
  });
  return result.sort((a, b) => a.name.localeCompare(b.name));
});

const billColumns = [
  { key: "bill_no", label: "账单编号" },
  { key: "room_label", label: "房屋" },
  { key: "owner_name", label: "业主" },
  { key: "fee_name", label: "费用" },
  { key: "fee_version_label", label: "使用版本" },
  { key: "period", label: "账期" },
  { key: "amount", label: "金额" },
  { key: "status", label: "状态" }
];

const today = new Date().toISOString().split('T')[0];
feeForm.effective_date = today;
generateForm.period = today.slice(0, 7);
generateForm.due_date = today.slice(0, 8) + "30";

async function load() {
  [feeTypes.value, bills.value] = await Promise.all([
    propertyApi.listFeeTypes(),
    propertyApi.listBills()
  ]);
}

function resetForm() {
  Object.assign(feeForm, {
    name: "",
    billing_method: "fixed",
    amount: 0,
    cycle: "monthly",
    effective_date: today,
    description: ""
  });
  editingFee.value = null;
}

async function saveFeeType() {
  if (editingFee.value) {
    const result = await propertyApi.updateFeeType(editingFee.value.id, { ...feeForm });
    if (result.created_new_version) {
      message.value = `已创建新版本 ${result.version_label}`;
    } else {
      message.value = "已更新";
    }
    resetForm();
  } else {
    await propertyApi.createFeeType({ ...feeForm });
    resetForm();
    message.value = "已创建费用标准";
  }
  await load();
}

function editFee(fee) {
  editingFee.value = fee;
  Object.assign(feeForm, {
    name: fee.name,
    billing_method: fee.billing_method,
    amount: Number(fee.amount),
    cycle: fee.cycle,
    effective_date: fee.effective_date,
    description: fee.description || ""
  });
}

function cancelEdit() {
  resetForm();
}

async function showHistory(fee) {
  historyFee.value = fee;
  feeHistory.value = await propertyApi.getFeeTypeHistory(fee.id);
  historyVisible.value = true;
}

function closeHistory() {
  historyVisible.value = false;
  historyFee.value = null;
  feeHistory.value = [];
}

function toggleGroup(name) {
  const next = new Set(expandedGroups.value);
  if (next.has(name)) next.delete(name); else next.add(name);
  expandedGroups.value = next;
}

async function generate() {
  const result = await propertyApi.generateBills({ ...generateForm });
  const feeUsed = result.fee_type_used;
  message.value = `已生成 ${result.created_count} 条，跳过重复 ${result.skipped_count} 条，使用标准：${feeUsed.name} ${feeUsed.version_label}`;
  await load();
}

onMounted(load);
</script>

<style scoped>
.form-actions {
  display: flex;
  gap: 8px;
  grid-column: 1 / -1;
}

.form-actions .secondary {
  background: #e0e0e0;
  color: #333;
}

.notice.warn {
  background: #fff3cd;
  color: #856404;
  border: 1px solid #ffeeba;
}

.version-badge {
  display: inline-block;
  padding: 2px 8px;
  background: #e3f2fd;
  color: #1565c0;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.version-badge.small {
  padding: 1px 6px;
  font-size: 11px;
}

.status-badge.active {
  background: #e8f5e9;
  color: #2e7d32;
}

.status-badge.inactive {
  background: #f5f5f5;
  color: #757575;
}

button.link {
  background: none;
  border: none;
  color: #1976d2;
  padding: 4px 8px;
  cursor: pointer;
}

button.link:hover {
  text-decoration: underline;
}

.muted {
  color: #999;
  font-size: 12px;
}

.fee-groups {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  overflow: hidden;
}

.fee-group + .fee-group {
  border-top: 1px solid #e0e0e0;
}

.group-active-row {
  display: grid;
  grid-template-columns: 1.2fr 1.2fr 1fr 1fr 0.8fr 0.7fr 1.4fr;
  align-items: center;
  padding: 10px 12px;
  gap: 8px;
  cursor: pointer;
  background: #fafbfc;
  transition: background 0.15s;
}

.group-active-row:hover {
  background: #f0f7ff;
}

.row-col {
  font-size: 13px;
}

.col-name {
  font-weight: 600;
  color: #1a1a1a;
}

.col-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: flex-end;
}

.group-old-versions {
  background: #fafafa;
  border-top: 1px dashed #e0e0e0;
}

.group-old-row {
  display: grid;
  grid-template-columns: 1.2fr 1.2fr 1fr 1fr 0.8fr 0.7fr 1.4fr;
  align-items: center;
  padding: 8px 12px 8px calc(12px + 24px);
  gap: 8px;
  opacity: 0.75;
  border-bottom: 1px dotted #eee;
}

.group-old-row:last-child {
  border-bottom: none;
}

.status-badge.active,
.status-badge.inactive {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 800px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-head h3 {
  margin: 0;
}

.modal-head .close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  padding: 0 8px;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
}

.history-table {
  width: 100%;
  border-collapse: collapse;
}

.history-table th,
.history-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #e0e0e0;
}

.history-table th {
  background: #f5f5f5;
  font-weight: 600;
}

.history-table tbody tr:hover {
  background: #fafafa;
}
</style>
