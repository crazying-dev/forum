package media

import (
	"bytes"
	"image"
	"image/color"
	"strconv"
	"strings"
	"testing"
)

// testImage 构造带渐变的测试图（避免纯色压缩后体积过小）。
func testImage(w, h int) image.Image {
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			img.Set(x, y, color.RGBA{R: uint8(x % 256), G: uint8(y % 256), B: 128, A: 255})
		}
	}
	return img
}

// TestBuildVariantsScales 验证等比缩放尺寸与变体元数据。
func TestBuildVariantsScales(t *testing.T) {
	const id = "MD0123456789abcdef"
	got, err := buildVariants(testImage(2000, 1000), id, "post_image", "2026/10")
	if err != nil {
		t.Fatalf("buildVariants 失败: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("变体数量 = %d, want 2", len(got))
	}

	want := []struct {
		variant   string
		width     int
		height    int
		keySuffix string
	}{
		{"w480", 480, 240, "@480.jpg"},
		{"w1280", 1280, 640, "@1280.jpg"},
	}
	for i, tc := range want {
		v := got[i]
		if v.Variant != tc.variant {
			t.Errorf("变体[%d] = %q, want %q", i, v.Variant, tc.variant)
		}
		if v.Width != tc.width || v.Height != tc.height {
			t.Errorf("%s 尺寸 = %dx%d, want %dx%d", v.Variant, v.Width, v.Height, tc.width, tc.height)
		}
		if v.Mime != "image/jpeg" {
			t.Errorf("%s mime = %q, want image/jpeg", v.Variant, v.Mime)
		}
		if !strings.HasSuffix(v.ObjectKey, tc.keySuffix) {
			t.Errorf("%s object_key = %q, 应以 %q 结尾", v.Variant, v.ObjectKey, tc.keySuffix)
		}
		if !strings.HasPrefix(v.ObjectKey, "post_image/") || !strings.Contains(v.ObjectKey, id+"@") {
			t.Errorf("%s object_key = %q, 不符合 scene/YYYY/MM/<id>@<w>.jpg", v.Variant, v.ObjectKey)
		}
		if v.SHA256 == "" || len(v.Data) == 0 {
			t.Errorf("%s 缺少 sha256 或字节", v.Variant)
		}
		img, err := jpegDecode(v.Data)
		if err != nil {
			t.Fatalf("%s 不是合法 JPEG: %v", v.Variant, err)
		}
		if b := img.Bounds(); b.Dx() != tc.width || b.Dy() != tc.height {
			t.Errorf("%s 实际编码尺寸 = %dx%d, want %dx%d", v.Variant, b.Dx(), b.Dy(), tc.width, tc.height)
		}
	}
}

// TestBuildVariantsSkipsSmallImage 验证原图不宽于目标宽度时不放大（含边界）。
func TestBuildVariantsSkipsSmallImage(t *testing.T) {
	cases := []struct {
		name  string
		w, h  int
		count int
	}{
		{"远小于最小档", 300, 200, 0},
		{"等于 480", 480, 240, 0},
		{"略超 480", 481, 240, 1},
		{"介于两档之间", 1000, 500, 1},
		{"等于 1280", 1280, 640, 1}, // 仅 480 档生成（1280 不放大）
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := buildVariants(testImage(tc.w, tc.h), "MD0123456789abcdef", "post_image", "2026/10")
			if err != nil {
				t.Fatalf("buildVariants 失败: %v", err)
			}
			if len(got) != tc.count {
				t.Fatalf("%dx%d 变体数量 = %d, want %d", tc.w, tc.h, len(got), tc.count)
			}
		})
	}
}

// TestBuildVariantsPaletted 验证调色板 PNG 也会生成变体（GIF 在 prepareUpload 层按 MIME 拦截）。
func TestBuildVariantsPaletted(t *testing.T) {
	pal := image.NewPaletted(image.Rect(0, 0, 2000, 1000), color.Palette{color.Black, color.White})
	got, err := buildVariants(pal, "MD0123456789abcdef", "post_image", "2026/10")
	if err != nil {
		t.Fatalf("buildVariants 失败: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("调色板 PNG 应生成 2 档变体，got %d", len(got))
	}
}

// TestVariantName 验证变体命名与读路径白名单一致。
func TestVariantName(t *testing.T) {
	for _, w := range variantWidths {
		if got, want := variantName(w), "w"+strconv.Itoa(w); got != want {
			t.Fatalf("variantName(%d) = %q, want %q", w, got, want)
		}
	}
}

// jpegDecode 解码 JPEG 字节（测试辅助）。
func jpegDecode(data []byte) (image.Image, error) {
	img, _, err := image.Decode(bytes.NewReader(data))
	return img, err
}
