"""
Polymarket 头寸恢复工具（通用版）
===============================
适用场景：
- V2 迁移后头寸/余额无法在前端显示
- 邮箱（Magic Link）登录用户无法通过官方界面操作
- 需要直接通过链上合约赎回获胜头寸并提取 USDC.e

使用方法：
1. 安装依赖：py -m pip install web3 eth-abi
2. 填写下方配置区
3. 运行：py polymarket_recovery.py

原理：
- 通过 Polymarket ProxyWalletFactory 合约的 proxy() 函数转发调用
- EOA（邮箱私钥）→ ProxyWalletFactory → 代理钱包 → 目标合约
- Polygon 网络 gas 费极低（约 $0.002）
"""

from web3 import Web3
from eth_abi import encode
from getpass import getpass

# ============================================================
# 第一步：填写配置
# ============================================================

# Polygon RPC（推荐用自己的，免费注册：infura.io 或 alchemy.com）
RPC_URL = "https://polygon-mainnet.infura.io/v3/你的KEY"

# 提取目标地址（你的外部钱包，USDC.e 会发到这里）
TO_ADDRESS = "0x你的外部钱包地址"

# 要赎回的市场信息（从 Polymarket Data API 获取）
# 查询方法：https://data-api.polymarket.com/positions?user=你的代理钱包地址&sizeThreshold=0
CONDITION_ID = "0x你的conditionId"       # 市场的 conditionId
INDEX_SETS   = [1, 2]                    # 通常填 [1, 2]，代表赎回所有结果

# ============================================================
# 固定合约地址（Polygon 主网，无需修改）
# ============================================================
FACTORY = "0xaB45c5A4B0c941a2F231C04c3F49182e1a254052"  # ProxyWalletFactory
CTF     = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"  # ConditionalTokens
USDC_E  = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e

FACTORY_ABI = [{
    "name": "proxy",
    "type": "function",
    "inputs": [{"name": "calls", "type": "tuple[]", "components": [
        {"name": "typeCode", "type": "uint8"},
        {"name": "to",       "type": "address"},
        {"name": "value",    "type": "uint256"},
        {"name": "data",     "type": "bytes"}
    ]}],
    "outputs": [{"name": "", "type": "bytes[]"}]
}]

CTF_ABI = [{
    "name": "balanceOf",
    "type": "function",
    "inputs": [
        {"name": "owner", "type": "address"},
        {"name": "id",    "type": "uint256"}
    ],
    "outputs": [{"name": "", "type": "uint256"}]
}]

USDC_ABI = [{
    "name": "balanceOf",
    "type": "function",
    "inputs": [{"name": "account", "type": "address"}],
    "outputs": [{"name": "", "type": "uint256"}]
}, {
    "name": "transfer",
    "type": "function",
    "inputs": [
        {"name": "recipient", "type": "address"},
        {"name": "amount",    "type": "uint256"}
    ],
    "outputs": [{"name": "", "type": "bool"}]
}]

# ============================================================
# 工具函数
# ============================================================

def make_redeem_calldata(condition_id: str, index_sets: list) -> bytes:
    """构造 redeemPositions calldata"""
    selector = bytes.fromhex("01b7037c")
    params = encode(
        ['address', 'bytes32', 'bytes32', 'uint256[]'],
        [
            Web3.to_checksum_address(USDC_E),
            b'\x00' * 32,
            bytes.fromhex(condition_id.replace("0x", "")),
            index_sets
        ]
    )
    return selector + params

def make_transfer_calldata(to: str, amount: int) -> bytes:
    """构造 ERC20 transfer calldata"""
    selector = bytes.fromhex("a9059cbb")
    params = encode(['address', 'uint256'], [Web3.to_checksum_address(to), amount])
    return selector + params

def send_via_factory(w3, account, factory, calls, gas=500_000):
    """通过 ProxyWalletFactory 发送交易"""
    tx = factory.functions.proxy(calls).build_transaction({
        "from":     account.address,
        "nonce":    w3.eth.get_transaction_count(account.address),
        "gas":      gas,
        "gasPrice": w3.eth.gas_price,
        "chainId":  137
    })
    signed   = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash  = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"   交易哈希: {tx_hash.hex()}")
    print(f"   查看: https://polygonscan.com/tx/{tx_hash.hex()}")
    receipt  = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    return receipt

# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 55)
    print("  Polymarket 头寸恢复工具")
    print("=" * 55)

    # 输入私钥
    private_key = getpass("\n请输入私钥（不显示）：")
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    # 连接网络
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌ 无法连接到 Polygon，请检查 RPC_URL")
        return
    print("✅ 已连接到 Polygon 网络")

    # 加载账户
    account = w3.eth.account.from_key(private_key)
    print(f"✅ EOA 地址: {account.address}")

    # 初始化合约
    factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY), abi=FACTORY_ABI)
    usdc    = w3.eth.contract(address=Web3.to_checksum_address(USDC_E),   abi=USDC_ABI)

    # ── 第一步：赎回获胜头寸 ──────────────────────────────
    print("\n📋 第一步：赎回头寸...")
    redeem_data = make_redeem_calldata(CONDITION_ID, INDEX_SETS)
    receipt = send_via_factory(w3, account, factory, [
        (1, Web3.to_checksum_address(CTF), 0, redeem_data)
    ])
    if receipt["status"] == 1:
        print("   ✅ 赎回成功！")
    else:
        print("   ❌ 赎回失败，请检查 CONDITION_ID 和 INDEX_SETS")
        return

    # ── 等待余额上链 ──────────────────────────────────────
    import time
    print("\n⏳ 等待 15 秒让余额上链...")
    for i in range(15, 0, -1):
        print(f"   {i} 秒...", end="\r")
        time.sleep(1)
    print("   ✅ 等待完成       ")

    # ── 查询代理钱包 USDC.e 余额 ─────────────────────────
    # 通过工厂 proxy() 的 staticcall 无法直接查，改用 Data API
    print("\n💰 查询余额...")
    import urllib.request, json
    try:
        url = f"https://data-api.polymarket.com/value?user={account.address}"
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read())
            value = data[0].get("value", 0) if data else 0
            print(f"   代理钱包价值: ${value}")
    except Exception:
        print("   （无法查询 API，继续尝试提取）")

    # ── 第二步：提取 USDC.e 到外部钱包 ───────────────────
    print(f"\n📤 第二步：提取 USDC.e 到 {TO_ADDRESS}...")

    # 尝试提取 300 USDC.e（6位小数）
    # 如果不确定金额，可以先查余额再填
    amount = 300_000_000  # 300 USDC.e，按实际修改

    transfer_data = make_transfer_calldata(TO_ADDRESS, amount)
    receipt = send_via_factory(w3, account, factory, [
        (1, Web3.to_checksum_address(USDC_E), 0, transfer_data)
    ], gas=300_000)

    if receipt["status"] == 1:
        print(f"   ✅ 提取成功！{amount / 1_000_000:.2f} USDC.e 已发送到 {TO_ADDRESS}")
    else:
        print("   ❌ 提取失败，可能余额不足或地址不对")

    print("\n完成！")

if __name__ == "__main__":
    main()
