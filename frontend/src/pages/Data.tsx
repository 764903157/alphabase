import { useState } from "react";
import { Table, Button, Space, message, Tag, Input, Form, Modal, Select, Typography } from "antd";
import { CloudDownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import { dataApi } from "../api/data";

const { Text } = Typography;

export default function Data() {
  const [loading, setLoading] = useState(false);
  const [stockList, setStockList] = useState<any[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const loadStocks = async () => {
    setLoading(true);
    try {
      const r = await dataApi.getStocks();
      setStockList(r.data.data || []);
      if ((r.data.data || []).length === 0) {
        message.info("未找到股票列表，请检查数据源配置");
      }
    } catch (e: any) {
      message.error("加载股票列表失败: " + (e?.message || "未知错误"));
    } finally {
      setLoading(false);
    }
  };

  const fetchAndSave = async (values: any) => {
    setSaving(true);
    try {
      const r = await dataApi.saveKline({
        code: values.code,
        start: values.start,
        end: values.end || undefined,
        freq: values.freq || "day",
        adjust: values.adjust || "qfq",
      });
      message.success(`已保存 ${r.data.saved} 条 ${values.code} ${values.freq} 数据`);
      setModalOpen(false);
      form.resetFields();
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "未知错误";
      message.error("保存失败: " + detail);
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    { title: "代码", dataIndex: "code", width: 120 },
    { title: "名称", dataIndex: "name", width: 120 },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button
          icon={<ReloadOutlined />}
          onClick={loadStocks}
          loading={loading}
        >
          加载股票列表
        </Button>
        <Button
          type="primary"
          icon={<CloudDownloadOutlined />}
          onClick={() => setModalOpen(true)}
        >
          下载数据
        </Button>
      </Space>

      {stockList.length > 0 && (
        <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
          共 {stockList.length} 支股票
        </Text>
      )}

      <Table
        size="small"
        loading={loading}
        columns={columns}
        dataSource={stockList.map(s => ({ ...s, key: s.code }))}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title="下载行情数据"
        open={modalOpen}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        onOk={() => form.validateFields().then(fetchAndSave)}
        okText="下载并保存"
        cancelText="取消"
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" initialValues={{ freq: "day", adjust: "qfq" }}>
          <Form.Item name="code" label="股票代码" rules={[{ required: true, message: "请输入股票代码" }]}>
            <Input placeholder="如 600000.SH" />
          </Form.Item>
          <Form.Item name="freq" label="频率">
            <Select>
              <Select.Option value="day">日线</Select.Option>
              <Select.Option value="1min">1分钟</Select.Option>
              <Select.Option value="5min">5分钟</Select.Option>
              <Select.Option value="15min">15分钟</Select.Option>
              <Select.Option value="30min">30分钟</Select.Option>
              <Select.Option value="60min">60分钟</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="adjust" label="复权类型">
            <Select>
              <Select.Option value="qfq">前复权</Select.Option>
              <Select.Option value="hfq">后复权</Select.Option>
              <Select.Option value="none">不复权</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="start" label="开始日期" rules={[{ required: true, message: "请输入开始日期" }]}>
            <Input placeholder="YYYYMMDD 如 20240101" />
          </Form.Item>
          <Form.Item name="end" label="结束日期">
            <Input placeholder="YYYYMMDD 如 20250501（留空为今天）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}