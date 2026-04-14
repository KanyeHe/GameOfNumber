# GameOfNumber
数字游戏

## 本地运行
安装依赖：
`pip install PyQt6`

配置服务地址（可选，默认分别为 `http://localhost:8001` 和 `http://localhost:8002`）：
`export SUBSCRIPTION_CENTER_BASE=http://localhost:8001`
`export GAME_BACKEND_BASE=http://localhost:8002`

启动：
`python app.py`

## 当前版本说明

当前客户端已切换为中心服务登录模型：

1. 先注册账号
2. 再登录
3. 启动时优先恢复本地登录态，必要时自动刷新 token
4. 登录后自动上报设备并查询当前订阅状态
5. 若无可用资格，优先自动尝试开通试用，否则引导创建支付订单
6. 通过 `sessions/enter-product` 获取产品态 token 和 `sessionNo`
7. 开奖数据和预测记录由数字游戏后端服务提供，统一使用产品态 token

接口和库表设计见：

1. `docs/center-migration.md`
2. `docs/central-api-contract.md`

## 打包可执行文件（可选）
`pip install pyinstaller`

`pyinstaller --onefile --windowed app.py`
