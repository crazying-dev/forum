package easteregg

import (
	"encoding/json"
	"testing"
)

// TestEmbeddedEasterEgg 验证内置 JSON 可解析且字段完整。
func TestEmbeddedEasterEgg(t *testing.T) {
	var list []struct {
		ID   string `json:"ID"`
		Name string `json:"Name"`
		Text string `json:"Text"`
	}
	if err := json.Unmarshal(JSON(), &list); err != nil {
		t.Fatalf("内置彩蛋 JSON 解析失败: %v", err)
	}
	if len(list) == 0 {
		t.Fatal("内置彩蛋为空")
	}
	if list[0].ID == "" || list[0].Name == "" || list[0].Text == "" {
		t.Fatalf("内置彩蛋字段缺失: %+v", list[0])
	}
}
