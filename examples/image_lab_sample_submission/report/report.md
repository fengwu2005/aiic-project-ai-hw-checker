# ImageLab 学生报告

## 一、项目实现方法

我实现的 ImageLab 是一个基于 Pillow/PIL 的命令行图像变换工具。核心思路是让 `load_image` 统一读取并转换为 RGB 图像，然后让每个变换函数接收 Image 对象并返回新的 Image 对象。命令行层只负责解析参数，真正的业务逻辑集中在 `resize_image`、`crop_image`、`invert_image`、`blur_image`、`edge_detect` 和 `median_filter` 等函数中。

## 二、关键功能说明

`resize_image` 根据比例计算新尺寸，并拒绝小于等于 0 的比例。`crop_image` 会检查裁剪框是否在图片范围内，避免无效坐标产生难以解释的输出。`invert_image` 使用 RGB 图像进行反色，避免不同图像模式导致的错误。

模糊和中值滤波是我重点修改的部分。均值模糊使用 3x3 邻域，计算每个通道的平均值；中值滤波收集窗口内每个通道的像素值并取中位数，用来去除孤立噪点。边缘检测使用固定 Laplacian 卷积核，先取响应强度的绝对值，再通过 `_clamp` 限制结果在 0 到 255。

`transform_image` 是统一调度入口，支持 resize、rotate、crop、invert、blur、edge 和 median。未知操作会抛出 `ValueError`，而不是静默保存原图。

## 三、关键贡献

- 统一最终函数接口，保证系统可以直接调用每个图像处理函数。
- 让 `load_image` 统一转换为 RGB，减少模式差异导致的问题。
- 增加缩放比例、裁剪框、滤波窗口和未知操作校验。
- 手写均值模糊、中值滤波和固定卷积核边缘检测。
- 设计 `transform_image` 作为 CLI 和业务函数之间的稳定调度层。

## 四、系统验收准备与自查方法

我根据作业要求检查了固定函数接口，确保 `load_image`、`save_image`、`resize_image`、`rotate_image`、`crop_image`、`invert_image`、`blur_image`、`edge_detect`、`median_filter` 和 `transform_image` 都可以被外部直接调用。

我手动构造小尺寸测试图片，分别检查缩放尺寸、裁剪像素、反色结果、均值模糊中心像素、边缘检测强度和中值滤波去噪效果。

具体自查输入包括：

- 2x2 黑白图片：验证 `invert_image` 是否把 `(0,0,0)` 变成 `(255,255,255)`。
- 4x4 渐变图片：验证 `crop_image(image, 1, 1, 3, 3)` 是否返回 2x2 区域。
- 5x5 中心亮点图片：验证 `blur_image` 后中心亮点被邻域平均削弱。
- 5x5 孤立噪点图片：验证 `median_filter` 能去除单点噪声。
- 平坦区域和边界区域混合图片：验证 `edge_detect` 对边界位置给出更高响应。
- 非法 `scale=0`、越界裁剪框、偶数滤波窗口：验证代码会抛出 `ValueError`。

## 五、最终反思

这个项目最大的难点不是调用 Pillow API，而是把接口稳定下来，把边界场景测清楚，并能说明每个图像操作背后的原因。均值模糊、中值滤波和边缘检测都需要理解窗口、通道和像素范围；如果只会运行命令但解释不了这些细节，说明并没有真正掌握。
