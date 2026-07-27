WITH weekly_uid AS (
  SELECT COUNT(DISTINCT uid) AS total_uid
  FROM dwd_ima_activity_coupon_uid_aggr_di
  WHERE imp_date >= {START} AND imp_date <= {END}
    AND coupon_cnt > 0
),
user_weekly AS (
  SELECT
    uid,
    SUM(coupon_cnt_management) AS wk_mgmt,
    SUM(coupon_cnt_skill) AS wk_skill
  FROM dwd_ima_activity_coupon_uid_aggr_di
  WHERE imp_date >= {START} AND imp_date <= {END}
  GROUP BY uid
)
SELECT
  COUNT(DISTINCT CASE WHEN u.wk_mgmt > 0 THEN u.uid END) AS kb_people,
  COUNT(DISTINCT CASE WHEN u.wk_skill > 0 THEN u.uid END) AS sk_people,
  MAX(w.total_uid) AS total_people
FROM user_weekly u
CROSS JOIN weekly_uid w
