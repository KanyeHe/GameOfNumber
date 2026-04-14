# 中心化改造说明

## 1. 现有 SQLite 结构

当前客户端本地只有两张业务表：

### `draw_results`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | TEXT PK | 期号 |
| `name` | TEXT | 彩种名称 |
| `date` | TEXT | 开奖时间 |
| `red` | TEXT | 开奖号码，格式 `x,x,x` |
| `hundreds_place` | INTEGER | 百位 |
| `tens_place` | INTEGER | 十位 |
| `units_place` | INTEGER | 个位 |

### `prediction_records`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | TEXT PK | 预测对应期号 |
| `red` | TEXT | 实际开奖号 |
| `status` | TEXT | `待开奖` / `已开奖` |
| `danma_selection` | TEXT | 用户自选胆码，逗号分隔 |
| `ai_recommendation` | TEXT | 旧字段，当前基本未使用 |
| `ai_hundreds` | TEXT | AI 百位基础推荐 |
| `ai_tens` | TEXT | AI 十位基础推荐 |
| `ai_units` | TEXT | AI 个位基础推荐 |
| `hundreds_dan` | TEXT | 百位最终胆码 |
| `tens_dan` | TEXT | 十位最终胆码 |
| `units_dan` | TEXT | 个位最终胆码 |

## 2. MySQL 表结构建议

`draw_results` 属于全局开奖数据，不归属某个账号；`prediction_records` 属于用户生成数据，需要挂到 `t_account.id`。

```sql
DROP TABLE IF EXISTS `gon_draw_result`;
CREATE TABLE `gon_draw_result` (
  `id`                BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `product_code`      VARCHAR(64) NOT NULL DEFAULT 'GAME_OF_NUMBER' COMMENT '产品编码',
  `draw_code`         VARCHAR(64) NOT NULL COMMENT '期号',
  `lottery_name`      VARCHAR(64) NOT NULL COMMENT '彩种名称',
  `draw_time`         DATETIME NOT NULL COMMENT '开奖时间',
  `draw_red`          VARCHAR(32) NOT NULL COMMENT '开奖结果，如 1,2,3',
  `hundreds_place`    TINYINT NOT NULL COMMENT '百位',
  `tens_place`        TINYINT NOT NULL COMMENT '十位',
  `units_place`       TINYINT NOT NULL COMMENT '个位',
  `create_time`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_product_draw_code` (`product_code`, `draw_code`) USING BTREE,
  KEY `idx_draw_time` (`draw_time`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='游戏开奖表';

DROP TABLE IF EXISTS `gon_prediction_record`;
CREATE TABLE `gon_prediction_record` (
  `id`                BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `account_id`        BIGINT NOT NULL COMMENT '账号ID，关联 t_account.id',
  `product_code`      VARCHAR(64) NOT NULL DEFAULT 'GAME_OF_NUMBER' COMMENT '产品编码',
  `draw_code`         VARCHAR(64) NOT NULL COMMENT '期号',
  `draw_red`          VARCHAR(32) DEFAULT NULL COMMENT '实际开奖号',
  `status`            VARCHAR(16) NOT NULL COMMENT 'PENDING/RESOLVED',
  `danma_selection`   VARCHAR(64) DEFAULT NULL COMMENT '用户自选胆码',
  `ai_hundreds`       VARCHAR(64) DEFAULT NULL COMMENT 'AI百位推荐',
  `ai_tens`           VARCHAR(64) DEFAULT NULL COMMENT 'AI十位推荐',
  `ai_units`          VARCHAR(64) DEFAULT NULL COMMENT 'AI个位推荐',
  `hundreds_dan`      VARCHAR(64) DEFAULT NULL COMMENT '百位胆码',
  `tens_dan`          VARCHAR(64) DEFAULT NULL COMMENT '十位胆码',
  `units_dan`         VARCHAR(64) DEFAULT NULL COMMENT '个位胆码',
  `source_type`       VARCHAR(32) NOT NULL DEFAULT 'DESKTOP' COMMENT '来源',
  `create_time`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_account_product_draw` (`account_id`, `product_code`, `draw_code`) USING BTREE,
  KEY `idx_account_status` (`account_id`, `status`) USING BTREE,
  CONSTRAINT `fk_gon_prediction_account`
    FOREIGN KEY (`account_id`) REFERENCES `t_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='用户预测记录表';
```

## 3. 迁移关系

1. `draw_results.code -> gon_draw_result.draw_code`
2. `prediction_records.code -> gon_prediction_record.draw_code`
3. `prediction_records.red -> gon_prediction_record.draw_red`
4. `prediction_records.status`
   本地值 `待开奖` 映射为 `PENDING`
   本地值 `已开奖` 映射为 `RESOLVED`
5. `prediction_records.*胆码字段` 原样迁移到 `gon_prediction_record`
6. 新增 `account_id`
   中心化后每条预测记录都必须归属 `t_account`

## 4. 迁移建议

1. 先上线账号体系、订阅体系、设备体系。
2. 服务端提供开奖数据同步任务，不再由桌面客户端直连福彩官网。
3. 客户端只保留 token、本机设备信息、少量 UI 状态，本地不再存业务数据。
4. 如要迁移已有单机数据，可提供一次性导入接口：
   `POST /api/v1/game-of-number/migrations/local-data`
   由已登录用户上传本地 SQLite 导出的 JSON，服务端按 `account_id` 入库。
