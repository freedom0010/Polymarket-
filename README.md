# Polymarket 头寸恢复工具

通过 Polymarket ProxyWalletFactory 合约直接操作链上资产，
适用于 V2 迁移后无法通过前端界面访问头寸和余额的用户。

---

## 环境配置

### 1. 安装 Python

从 python.org 下载安装，安装时勾选 "Add Python to PATH"

### 2. 安装依赖

```
py -m pip install web3 eth-abi
```

### 3. 获取 Polygon RPC

免费注册任意一个：
- https://infura.io → 新建项目 → 复制 Polygon Mainnet URL
- https://www.alchemy.com → 新建 App → 选 Polygon → 复制 HTTPS URL

---

## 使用步骤

### 第一步：获取私钥

访问 https://reveal.magic.link/polymarket，用邮箱登录，导出私钥（0x开头，66位字符）

### 第二步：获取市场信息

在浏览器打开（替换为你的代理钱包地址）：
```
https://data-api.polymarket.com/positions?user=你的代理钱包地址&sizeThreshold=0
```

从返回的 JSON 中找到：
- `conditionId`：市场条件 ID
- `proxyWallet`：确认是你的地址

### 第三步：填写配置

打开 `polymarket_recovery.py`，修改以下内容：

```python
RPC_URL      = "https://polygon-mainnet.infura.io/v3/你的KEY"
TO_ADDRESS   = "0x你的外部钱包地址"    # USDC.e 提取目标
CONDITION_ID = "0x你的conditionId"     # 从 API 查到的
INDEX_SETS   = [1, 2]                  # 通常填 [1, 2]
```

同时修改提取金额（默认 300）：
```python
amount = 300_000_000  # 300 USDC.e，1 USDC.e = 1_000_000
```

### 第四步：运行

```
py polymarket_recovery.py
```

输入私钥后自动执行：
1. 赎回获胜头寸（redeemPositions）
2. 提取 USDC.e 到你的外部钱包（transfer）

---

## 原理说明

```
EOA（邮箱私钥）
    ↓
ProxyWalletFactory.proxy()
    ↓ 自动找到对应代理钱包
代理钱包
    ↓
CTF.redeemPositions() → 获胜 token 换成 USDC.e
USDC.transfer()       → USDC.e 转到外部钱包
```

---

## 常见问题

**Q: 私钥长度报错**
A: 确保私钥是 0x 开头的 66 位字符串，重新从 reveal.magic.link/polymarket 导出

**Q: 无法连接 Polygon**
A: 换一个 RPC，或检查网络是否能访问 infura.io

**Q: 赎回失败（payout: 0）**
A: 市场还未结算，等结算后再运行；或 conditionId 填写有误

**Q: 提取失败（transfer amount exceeds balance）**
A: 代理钱包余额不足，可能赎回还未到账，等几分钟再试；或 amount 填写有误

---

## 安全提示

- 私钥只在本地输入，不保存在代码里
- 不要把私钥发给任何人，包括客服
- 运行完成后清空终端历史记录
