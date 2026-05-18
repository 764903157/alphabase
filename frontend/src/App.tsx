import { Routes, Route, Navigate } from "react-router-dom";
import { Layout, Menu } from "antd";
import { useNavigate, useLocation } from "react-router-dom";
import Research from "./pages/Research";
import BacktestReport from "./pages/BacktestReport";
import Data from "./pages/Data";
import Settings from "./pages/Settings";

const { Header, Sider, Content } = Layout;

function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    { key: "/research", label: "研究" },
    { key: "/backtest", label: "回测报告" },
    { key: "/data", label: "数据" },
    { key: "/settings", label: "设置" },
  ];

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#141414", color: "#e0e0e0" }}>
      <Layout style={{ minHeight: "100vh" }}>
        <Header style={{ color: "white", fontSize: 18, paddingLeft: 16 }}>
          AlphaBase Web
        </Header>
        <Layout>
          <Sider width={180}>
            <Menu
              mode="inline"
              selectedKeys={[location.pathname]}
              items={menuItems}
              onClick={({ key }) => navigate(key)}
              style={{ height: "100%", backgroundColor: "#1a1a1a" }}
              theme="dark"
            />
          </Sider>
          <Content style={{ padding: 16 }}>
            <Routes>
              <Route path="/" element={<Navigate to="/research" replace />} />
              <Route path="/research" element={<Research />} />
              <Route path="/backtest" element={<BacktestReport />} />
              <Route path="/data" element={<Data />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </div>
  );
}

export default App;