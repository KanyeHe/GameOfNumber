# 中心服务接口清单

## 服务划分

### 订阅中心 `http://localhost:8001`

这些接口已由客户端接入：

1. `POST /api/v1/auth/register`
2. `POST /api/v1/auth/login`
3. `POST /api/v1/auth/refresh-token`
4. `GET /api/v1/auth/me`
5. `GET /api/v1/products/detail?productCode=GAME_OF_NUMBER`
6. `POST /api/v1/subscriptions/trial/open`
7. `POST /api/v1/devices/upsert`
8. `POST /api/v1/sessions/create`
9. `GET /api/v1/subscriptions/access/check`
10. `POST /api/v1/payments/orders`

### 数字游戏后端服务 `http://localhost:8002`

以下是 Game Of Number 业务接口。

客户端本地访问中心服务时，至少还需要以下接口：

### 1. 最新开奖列表

`GET /api/v1/game-of-number/draws/latest?limit=10`

返回示例：

```json
{
  "success": true,
  "data": [
    {
      "code": "2026079",
      "name": "3D",
      "date": "2026-04-13 21:15:00",
      "red": "1,2,3",
      "hundredsPlace": 1,
      "tensPlace": 2,
      "unitsPlace": 3
    }
  ]
}
```

### 2. 按期号查询开奖

`GET /api/v1/game-of-number/draws/by-code?code=2026079`

### 3. 最近 N 天统计结果

`GET /api/v1/game-of-number/stats/recent-days?days=7`

返回示例：

```json
{
  "success": true,
  "data": {
    "hundreds_place": {
      "top_2": [1, 7],
      "bottom_2": [3, 6],
      "middle_1": [8],
      "random_2": [0, 9]
    },
    "tens_place": {},
    "units_place": {}
  }
}
```

### 4. 查询当前用户预测记录

`GET /api/v1/game-of-number/predictions?limit=50`

说明：
服务端根据登录态自动按 `account_id` 过滤，只返回当前用户数据。

### 5. 保存或更新待开奖预测

`POST /api/v1/game-of-number/predictions`

请求示例：

```json
{
  "code": "2026080",
  "status": "PENDING",
  "danmaSelection": "1,2,3",
  "aiHundreds": "1,4,8,9",
  "aiTens": "0,2,6,7",
  "aiUnits": "2,3,5,8",
  "hundredsDan": "1,2,4,6,7,8,9",
  "tensDan": "0,1,2,4,6,7,9",
  "unitsDan": "1,2,3,5,6,8,9"
}
```

服务端要求：

1. 根据 access token 解析 `account_id`
2. 对 `(account_id, product_code, draw_code)` 做 upsert
3. 自动补充 `product_code=GAME_OF_NUMBER`

### 6. 更新历史验证结果

`PUT /api/v1/game-of-number/predictions/{code}`

请求示例：

```json
{
  "hundredsDan": "1,2,4,6,7,8,9",
  "tensDan": "0,1,2,4,6,7,9",
  "unitsDan": "1,2,3,5,6,8,9"
}
```

### 7. 一次性导入本地 SQLite 数据

`POST /api/v1/game-of-number/migrations/local-data`

用途：
老版本桌面端升级后，将本地历史记录上传到当前账号下。

## 服务端处理建议

1. 开奖数据统一由服务端定时任务抓取并入库。
2. 客户端不再直接访问第三方福彩接口。
3. 预测记录、验证记录全部走账号隔离。
4. `GET /predictions`、`POST /predictions`、`PUT /predictions/{code}` 都必须校验当前登录用户和产品权限。
