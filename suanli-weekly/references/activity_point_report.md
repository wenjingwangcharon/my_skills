# 活动算力周报 — SQL 模板

## 底表

`dws_ima_qa_copilot_point_indic_aggr_di`

## 时间窗口参数（每次替换 4 处）

```
本周_start = {week_start}   本周_end = {week_end}
累计_上界 = {cum_end}
上周期_start = {prev_start}  上周期_end = {prev_end}
```

举例：本周 7/3-7/9 → `week_start=20260703, week_end=20260709, cum_end=20260709, prev_start=20260626, prev_end=20260702`

## 计算规则

- **算力**：底表单位为厘，÷100 保留 2 位小数
- **人数**：`COUNT(DISTINCT uid)` 整体去重
- **TOTAL 行**：算力列 = 各 CTE 聚合结果的 SUM；人数列 = week_detail/acc_detail 全局去重；累计付费用户 = paid_user_set 行数
- 无数据活动通过 `act_list LEFT JOIN` + `COALESCE` 补 0

## 活动映射

| sort_no | 活动 | midas_product_id |
|---|---|---|
| 1 | 邀好友送算力 | `ima_copilot_invite_bonus` |
| 2 | 购买算力 | `%copilot_pay%` |
| 3 | 知识号算力激励-领券 | `copilot_friend_coupon` |
| 4 | 知识号算力激励-兑换 | `copilot_coupon` |
| 5 | 每日登录福利 | `ima_copilot_daily_login_bonus` |
| 6 | 新用户首月福利 | `ima_copilot_first_month_bonus` |
| 7 | 新人福利 | `ima_copilot_new_user_bonus` / `_new` |
| 8 | copilot算力补贴 | `ima_copilot_grant_bonus` |
| 9 | copilot用户奖励 | `ima_copilot_user_bonus` |
| 10 | 下载双端领算力 | `copilot_download_bonus` |

## 输出列（18 列）

sort_no / 活动 / 本周下发算力 / 本周会话消耗算力 / 本周过期消耗算力 / 本周下发人数 / 本周消耗人数 / 本周过期人数 / 累计下发算力 / 累计会话消耗算力 / 累计过期消耗算力 / 累计下发人数 / 累计会话消耗人数 / 累计过期人数 / 上周下发算力 / 上周消耗算力 / 上周过期算力 / 累计付费用户

## 累计付费用户口径

- 全表 `midas_product_id LIKE '%copilot_pay%'` 且 `issued_point_amount_acc > 0` 的 uid 集合
- 每活动 = 该活动累计参与者 ∩ 上述集合
- TOTAL 行 = paid_user_set 总 COUNT(*)

## SQL 模板

将 `{week_start}` `{week_end}` `{cum_end}` `{prev_start}` `{prev_end}` 替换为实际日期后执行：

```sql
WITH
week_detail AS (
    SELECT
        imp_date,
        uid,
        CASE
            WHEN midas_product_id LIKE '%copilot_pay%'                                              THEN '购买算力'
            WHEN midas_product_id IN ('ima_copilot_new_user_bonus','ima_copilot_new_user_bonus_new') THEN '新人福利'
            WHEN midas_product_id = 'ima_copilot_daily_login_bonus'                                  THEN '每日登录福利'
            WHEN midas_product_id = 'ima_copilot_user_bonus'                                         THEN 'copilot用户奖励'
            WHEN midas_product_id = 'ima_copilot_invite_bonus'                                       THEN '邀好友送算力'
            WHEN midas_product_id = 'copilot_friend_coupon'                                          THEN '知识号算力激励-领券'
            WHEN midas_product_id = 'copilot_coupon'                                                 THEN '知识号算力激励-兑换'
            WHEN midas_product_id = 'ima_copilot_grant_bonus'                                        THEN 'copilot算力补贴'
            WHEN midas_product_id = 'ima_copilot_first_month_bonus'                                  THEN '新用户首月福利'
            WHEN midas_product_id = 'copilot_download_bonus'                                        THEN '下载双端领算力'
            ELSE midas_product_id
        END AS activity,
        issued_point_amount,
        consumed_point_amount,
        expired_point_amount
    FROM dws_ima_qa_copilot_point_indic_aggr_di
    WHERE imp_date BETWEEN {week_start} AND {week_end}
),
acc_detail AS (
    SELECT
        uid,
        CASE
            WHEN midas_product_id LIKE '%copilot_pay%'                                              THEN '购买算力'
            WHEN midas_product_id IN ('ima_copilot_new_user_bonus','ima_copilot_new_user_bonus_new') THEN '新人福利'
            WHEN midas_product_id = 'ima_copilot_daily_login_bonus'                                  THEN '每日登录福利'
            WHEN midas_product_id = 'ima_copilot_user_bonus'                                         THEN 'copilot用户奖励'
            WHEN midas_product_id = 'ima_copilot_invite_bonus'                                       THEN '邀好友送算力'
            WHEN midas_product_id = 'copilot_friend_coupon'                                          THEN '知识号算力激励-领券'
            WHEN midas_product_id = 'copilot_coupon'                                                 THEN '知识号算力激励-兑换'
            WHEN midas_product_id = 'ima_copilot_grant_bonus'                                        THEN 'copilot算力补贴'
            WHEN midas_product_id = 'ima_copilot_first_month_bonus'                                  THEN '新用户首月福利'
            WHEN midas_product_id = 'copilot_download_bonus'                                        THEN '下载双端领算力'
            ELSE midas_product_id
        END AS activity,
        issued_point_amount,
        consumed_point_amount,
        expired_point_amount
    FROM dws_ima_qa_copilot_point_indic_aggr_di
    WHERE imp_date <= {cum_end}
),
act_list AS (
    SELECT activity,
           CASE activity
               WHEN '邀好友送算力'       THEN 1
               WHEN '购买算力'           THEN 2
               WHEN '知识号算力激励-领券' THEN 3
               WHEN '知识号算力激励-兑换' THEN 4
               WHEN '每日登录福利'       THEN 5
               WHEN '新用户首月福利'     THEN 6
               WHEN '新人福利'           THEN 7
               WHEN 'copilot算力补贴'    THEN 8
               WHEN 'copilot用户奖励'    THEN 9
               WHEN '下载双端领算力'     THEN 10
           END AS sort_no
    FROM (
        SELECT DISTINCT
            CASE
                WHEN midas_product_id LIKE '%copilot_pay%'                                              THEN '购买算力'
                WHEN midas_product_id IN ('ima_copilot_new_user_bonus','ima_copilot_new_user_bonus_new') THEN '新人福利'
                WHEN midas_product_id = 'ima_copilot_daily_login_bonus'                                  THEN '每日登录福利'
                WHEN midas_product_id = 'ima_copilot_user_bonus'                                         THEN 'copilot用户奖励'
                WHEN midas_product_id = 'ima_copilot_invite_bonus'                                       THEN '邀好友送算力'
                WHEN midas_product_id = 'copilot_friend_coupon'                                          THEN '知识号算力激励-领券'
                WHEN midas_product_id = 'copilot_coupon'                                                 THEN '知识号算力激励-兑换'
                WHEN midas_product_id = 'ima_copilot_grant_bonus'                                        THEN 'copilot算力补贴'
                WHEN midas_product_id = 'ima_copilot_first_month_bonus'                                  THEN '新用户首月福利'
                WHEN midas_product_id = 'copilot_download_bonus'                                        THEN '下载双端领算力'
                ELSE midas_product_id
            END AS activity
        FROM dws_ima_qa_copilot_point_indic_aggr_di
    ) d
    WHERE activity IN (
        '邀好友送算力','购买算力','知识号算力激励-领券','知识号算力激励-兑换',
        '每日登录福利','新用户首月福利','新人福利','copilot算力补贴','copilot用户奖励',
        '下载双端领算力'
    )
),
week_amt AS (
    SELECT activity,
           SUM(issued_point_amount)   AS week_issued,
           SUM(consumed_point_amount) AS week_consumed,
           SUM(expired_point_amount)  AS week_expired
    FROM week_detail
    GROUP BY activity
),
week_users AS (
    SELECT activity,
           COUNT(DISTINCT CASE WHEN issued_point_amount   > 0 THEN uid END) AS week_issued_users,
           COUNT(DISTINCT CASE WHEN consumed_point_amount > 0 THEN uid END) AS week_consumed_users,
           COUNT(DISTINCT CASE WHEN expired_point_amount  > 0 THEN uid END) AS week_expired_users
    FROM week_detail
    GROUP BY activity
),
acc_amt AS (
    SELECT activity,
           SUM(issued_point_amount)   AS acc_issued,
           SUM(consumed_point_amount) AS acc_consumed,
           SUM(expired_point_amount)  AS acc_expired
    FROM acc_detail
    GROUP BY activity
),
acc_users AS (
    SELECT activity,
           COUNT(DISTINCT CASE WHEN issued_point_amount   > 0 THEN uid END) AS acc_issued_users,
           COUNT(DISTINCT CASE WHEN consumed_point_amount > 0 THEN uid END) AS acc_consumed_users,
           COUNT(DISTINCT CASE WHEN expired_point_amount  > 0 THEN uid END) AS acc_expired_users
    FROM acc_detail
    GROUP BY activity
),
paid_user_set AS (
    SELECT DISTINCT uid
    FROM dws_ima_qa_copilot_point_indic_aggr_di
    WHERE midas_product_id LIKE '%copilot_pay%'
      AND issued_point_amount_acc > 0
      AND imp_date <= {cum_end}
),
acc_paid_users AS (
    SELECT activity,
           COUNT(DISTINCT CASE WHEN uid IN (SELECT uid FROM paid_user_set) THEN uid END) AS acc_paid_uv
    FROM acc_detail
    GROUP BY activity
),
prev_week_amt AS (
    SELECT
        CASE
            WHEN midas_product_id LIKE '%copilot_pay%'                                              THEN '购买算力'
            WHEN midas_product_id IN ('ima_copilot_new_user_bonus','ima_copilot_new_user_bonus_new') THEN '新人福利'
            WHEN midas_product_id = 'ima_copilot_daily_login_bonus'                                  THEN '每日登录福利'
            WHEN midas_product_id = 'ima_copilot_user_bonus'                                         THEN 'copilot用户奖励'
            WHEN midas_product_id = 'ima_copilot_invite_bonus'                                       THEN '邀好友送算力'
            WHEN midas_product_id = 'copilot_friend_coupon'                                          THEN '知识号算力激励-领券'
            WHEN midas_product_id = 'copilot_coupon'                                                 THEN '知识号算力激励-兑换'
            WHEN midas_product_id = 'ima_copilot_grant_bonus'                                        THEN 'copilot算力补贴'
            WHEN midas_product_id = 'ima_copilot_first_month_bonus'                                  THEN '新用户首月福利'
            WHEN midas_product_id = 'copilot_download_bonus'                                        THEN '下载双端领算力'
            ELSE midas_product_id
        END AS activity,
        SUM(issued_point_amount)   AS prev_week_issued,
        SUM(consumed_point_amount) AS prev_week_consumed,
        SUM(expired_point_amount)  AS prev_week_expired
    FROM dws_ima_qa_copilot_point_indic_aggr_di
    WHERE imp_date BETWEEN {prev_start} AND {prev_end}
    GROUP BY 1
)
SELECT
    a.sort_no AS sort_no,
    a.activity AS 活动,
    ROUND(COALESCE(wa.week_issued,0)   / 100.0, 2)                       AS 本周下发算力,
    ROUND(COALESCE(wa.week_consumed,0) / 100.0, 2)                       AS 本周会话消耗算力,
    ROUND(COALESCE(wa.week_expired,0)  / 100.0, 2)                       AS 本周过期消耗算力,
    COALESCE(wu.week_issued_users,0)                                     AS 本周下发人数,
    COALESCE(wu.week_consumed_users,0)                                   AS 本周消耗人数,
    COALESCE(wu.week_expired_users,0)                                    AS 本周过期人数,
    ROUND(COALESCE(aa.acc_issued,0)   / 100.0, 2)                        AS 累计下发算力,
    ROUND(COALESCE(aa.acc_consumed,0) / 100.0, 2)                        AS 累计会话消耗算力,
    ROUND(COALESCE(aa.acc_expired,0)  / 100.0, 2)                        AS 累计过期消耗算力,
    COALESCE(au.acc_issued_users,0)                                      AS 累计下发人数,
    COALESCE(au.acc_consumed_users,0)                                    AS 累计会话消耗人数,
    COALESCE(au.acc_expired_users,0)                                     AS 累计过期人数,
    ROUND(COALESCE(pw.prev_week_issued,0)   / 100.0, 2)                  AS 上周下发算力,
    ROUND(COALESCE(pw.prev_week_consumed,0) / 100.0, 2)                  AS 上周消耗算力,
    ROUND(COALESCE(pw.prev_week_expired,0)  / 100.0, 2)                  AS 上周过期算力,
    COALESCE(ap.acc_paid_uv, 0)                                          AS 累计付费用户
FROM act_list a
LEFT JOIN week_amt       wa  ON a.activity = wa.activity
LEFT JOIN week_users     wu  ON a.activity = wu.activity
LEFT JOIN acc_amt        aa  ON a.activity = aa.activity
LEFT JOIN acc_users      au  ON a.activity = au.activity
LEFT JOIN acc_paid_users ap  ON a.activity = ap.activity
LEFT JOIN prev_week_amt  pw  ON a.activity = pw.activity
UNION ALL
SELECT
    999 AS sort_no,
    'TOTAL' AS 活动,
    ROUND((SELECT SUM(week_issued)   FROM week_amt) / 100.0, 2)               AS 本周下发算力,
    ROUND((SELECT SUM(week_consumed) FROM week_amt) / 100.0, 2)               AS 本周会话消耗算力,
    ROUND((SELECT SUM(week_expired)  FROM week_amt) / 100.0, 2)               AS 本周过期消耗算力,
    (SELECT COUNT(DISTINCT CASE WHEN issued_point_amount   > 0 THEN uid END) FROM week_detail) AS 本周下发人数,
    (SELECT COUNT(DISTINCT CASE WHEN consumed_point_amount > 0 THEN uid END) FROM week_detail) AS 本周消耗人数,
    (SELECT COUNT(DISTINCT CASE WHEN expired_point_amount  > 0 THEN uid END) FROM week_detail) AS 本周过期人数,
    ROUND((SELECT SUM(acc_issued)   FROM acc_amt) / 100.0, 2)                 AS 累计下发算力,
    ROUND((SELECT SUM(acc_consumed) FROM acc_amt) / 100.0, 2)                 AS 累计会话消耗算力,
    ROUND((SELECT SUM(acc_expired)  FROM acc_amt) / 100.0, 2)                 AS 累计过期消耗算力,
    (SELECT COUNT(DISTINCT CASE WHEN issued_point_amount   > 0 THEN uid END) FROM acc_detail) AS 累计下发人数,
    (SELECT COUNT(DISTINCT CASE WHEN consumed_point_amount > 0 THEN uid END) FROM acc_detail) AS 累计会话消耗人数,
    (SELECT COUNT(DISTINCT CASE WHEN expired_point_amount  > 0 THEN uid END) FROM acc_detail) AS 累计过期人数,
    ROUND((SELECT SUM(prev_week_issued)   FROM prev_week_amt) / 100.0, 2)    AS 上周下发算力,
    ROUND((SELECT SUM(prev_week_consumed) FROM prev_week_amt) / 100.0, 2)    AS 上周消耗算力,
    ROUND((SELECT SUM(prev_week_expired)  FROM prev_week_amt) / 100.0, 2)    AS 上周过期算力,
    (SELECT COUNT(*) FROM paid_user_set)                                     AS 累计付费用户
ORDER BY sort_no
```
