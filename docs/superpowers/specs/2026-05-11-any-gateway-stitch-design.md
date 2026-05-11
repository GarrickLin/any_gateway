# Any Gateway Stitch 视觉升级设计

日期：2026-05-11

## 背景

`docs/web_designs/stitch` 中提供了 Any Gateway 的视觉美化参考，覆盖登录页、Dashboard、Request Logs 和 Nexus 风格概念页。现有前端位于 `apps/react`，使用 React 19、Vite、TypeScript 和 Arco Design。目标是在不改变业务行为的前提下，将 Stitch 的浅色企业 AI gateway 管理台风格应用到现有应用。

## 范围

精修页面：

- `apps/react/src/pages/Login/index.tsx`
- `apps/react/src/components/Layout/index.tsx`
- `apps/react/src/pages/Dashboard/index.tsx`
- `apps/react/src/pages/Logs/index.tsx`

全局风格套用页面：

- `ApiKeys`
- `Chat`
- `Channels`
- `Groups`
- `Prices`
- `Vouchers`
- `Users`

不在本次范围内：

- 不引入 Tailwind。
- 不重写路由、权限、API 调用、状态管理或日志解析。
- 不新增无后端支持的入口，例如全局搜索、SSO、找回密码。
- 不重排未精修页面的信息结构。

## 推荐方案

采用“CSS 设计系统 + 轻量页面封装”。

`apps/react/src/index.css` 作为全局视觉层，定义 Stitch/Nexus 风格的设计令牌和 Arco 组件覆盖。重点页面通过少量 `ag-*` class 和局部 JSX 结构调整实现更接近设计稿的层级、间距和布局。其他页面依靠全局覆盖获得统一观感，保持原交互和信息结构。

放弃的方案：

- Arco 主题深改：当前页面存在大量 inline style，仅靠主题难以达到设计稿效果。
- 直接迁移 Stitch Tailwind HTML：视觉还原强，但会引入第二套样式体系，维护成本和回归风险较高。

## 设计系统

全局 CSS 定义以下视觉令牌：

- 背景：`surface`、`surface-container-lowest`、`surface-container-low`、`surface-container`、`surface-container-high`
- 品牌色：`primary`、`primary-container`、`primary-fixed`
- 辅助状态色：`tertiary`、`tertiary-fixed`、`error`、`error-container`
- 文本：`on-surface`、`on-surface-variant`、`outline`
- 边框：`outline-variant`
- 圆角：8px 为常规卡片/按钮上限，胶囊仅用于导航 active、badge 和少量状态元素
- 字体：优先使用系统字体栈；如引入 Web Font 成本过高，则用 CSS 字重和间距模拟 Manrope/Inter 的层级

全局覆盖 Arco 常用组件：

- `Card`
- `Table`
- `Button`
- `Input`
- `Select`
- `DatePicker`
- `Tag`
- `Modal`
- `Pagination`
- `Spin`

通用 class 命名使用 `ag-*` 前缀，例如：

- `ag-shell`
- `ag-sidebar`
- `ag-topbar`
- `ag-content`
- `ag-page-header`
- `ag-filter-panel`
- `ag-stat-grid`
- `ag-stat-card`
- `ag-data-panel`
- `ag-log-expand`

## Shell 与导航

`Layout` 改为 Nexus 管理台框架。

侧边栏：

- 浅灰半透明 surface 背景。
- 细边框分隔主内容。
- 品牌区展示图标和 `Gateway` / `AI Infrastructure`。
- 导航项保持现有权限控制。
- active 项使用浅蓝胶囊背景。
- 折叠态沿用当前 Arco Sider 行为。

顶部栏：

- 使用 sticky、轻透明背景和轻微模糊效果。
- 左侧展示系统名 `AI API Gateway` 和当前页面标题。
- 右侧展示用户名、角色 badge 和图标化退出按钮。
- 不新增全局搜索，避免产生无功能入口。

主内容：

- 使用 `#f8f9fb` 类画布。
- 内容区统一 24-32px 间距。
- 最大宽度约 1600px，避免宽屏表格过度拉伸。
- 保留页面自身滚动和表格横向滚动。

## Login

登录页以 Stitch 的安全登录设计为参考。

保留行为：

- LDAP 用户名/密码登录。
- 已登录自动跳转。
- 登录失败沿用后端错误文案。
- 登录成功写入 Zustand auth store 并跳转首页。

视觉调整：

- 使用现有 `/background.png` 叠加浅色网格和径向层次。
- 中央玻璃感登录卡。
- 品牌标题为 `Any Gateway`。
- 副标题为 `AI Infrastructure Security`。
- 输入框使用左侧图标和柔和背景。
- 主按钮使用品牌蓝。

不添加：

- Azure AD。
- Okta。
- Forgot password。
- 任何未实现的外部认证入口。

## Dashboard

Dashboard 保留现有数据流和交互。

保留行为：

- 日期范围筛选。
- 管理员用户名筛选。
- 查询、刷新、CSV 导出。
- 统计总览。
- 用量表和模型表。
- 个人余额/套餐状态。
- 消费券兑换。
- 限流进度展示。
- 表格排序和分页。

视觉调整：

- 增加页面标题区，使用 Stitch 的 `System Overview` / Dashboard 层级。
- 筛选区改为统一 filter panel。
- 统计卡改为 bento 风格卡片。
- 表格放入白底 data panel。
- 个人状态、兑换券和限流区域统一为信息面板。

## Logs

Logs 保留现有日志解析和展开逻辑。

保留行为：

- 管理员和普通用户使用各自日志 API。
- 日期、模型、用户名等筛选。
- 分页。
- 状态码标签。
- 展开后懒加载 request/response/messages。
- Markdown 渲染。
- OpenAI/Anthropic/Gemini 消息解析。
- warning、reasoning、tool_use、tool_result 展示。

视觉调整：

- 页面标题改为 Stitch Request Logs 风格。
- 筛选栏统一为 filter panel。
- 表格使用全局 Nexus 表格样式。
- 状态标签颜色保持语义。
- 展开内容使用更柔和的分组面板和 code/pre 样式。

## 其他页面

`ApiKeys`、`Chat`、`Channels`、`Groups`、`Prices`、`Vouchers`、`Users` 只做全局视觉套用。

允许的最小调整：

- 给页面根节点或主要容器增加 `ag-page`、`ag-data-panel` 等 class。
- 移除明显破坏全局风格的局部 inline 背景或边框。
- 调整卡片/表格外层间距。

不允许：

- 改表单字段。
- 改 API 调用。
- 改权限判断。
- 改分页、排序、过滤行为。
- 改页面信息结构。

## 错误、加载与空态

- 加载态继续使用 Arco `Spin`。
- 错误提示继续使用 Arco `Message`，文案来源不变。
- 空态沿用 Arco empty 机制。
- 表格和面板样式通过全局 CSS 统一。
- 日志展开中的 pre/code 使用统一浅色代码块样式。

## 验收标准

功能：

- 登录、登出、路由跳转可用。
- Dashboard 查询、刷新、导出、兑换券、排序、分页可用。
- Logs 查询、分页、展开、消息渲染可用。
- 未精修页面功能不受影响。

视觉：

- 应用整体接近 Stitch 的浅色企业 AI gateway 管理台风格。
- 未精修页面不再呈现默认 Arco demo 观感。
- 重点页面没有明显文本溢出、遮挡、重叠或不可读状态。
- 桌面和窄屏下主内容可滚动，表格不会撑破整体布局。

验证命令：

```bash
cd apps/react
npm run build
npm run lint
npm run dev
```

浏览器检查：

- `/login`
- `/dashboard`
- `/logs`
- `/apikeys` 或 `/channels`

## 风险与缓解

风险：全局 Arco CSS 覆盖影响未精修页面。

缓解：覆盖只针对常用组件的视觉属性，不改布局行为；必要时通过 `ag-shell` 作用域限制。

风险：现有 inline style 抵消全局样式。

缓解：重点页面局部替换为 class；其他页面只在明显破坏统一风格时做最小调整。

风险：视觉稿中存在未实现功能入口。

缓解：不添加无后端支持的入口，只复用视觉语言。

风险：日志页解析逻辑脆弱。

缓解：不改 `logParsing` 数据逻辑；只调整呈现层样式。
