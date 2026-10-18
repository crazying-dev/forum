package legacy

import (
	"testing"
)

func TestCompareVersions(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"1.3.18", "1.3.18", 0},
		{"1.3.17", "1.3.18", -1},
		{"1.4", "1.3.18", 1},
		{"Windows-V1.3.18", "1.3.18", 0},
		{"2.0", "2.0.0", 0},
		{"", "0.0.0", 0},
	}
	for _, tc := range cases {
		if got := CompareVersions(tc.a, tc.b); got != tc.want {
			t.Errorf("CompareVersions(%q,%q)=%d，期望 %d", tc.a, tc.b, got, tc.want)
		}
	}
}

func TestCheckRelease(t *testing.T) {
	m := fallbackManifest()
	payload := CheckRelease(m, "windows", "1.0.0")
	if payload == nil {
		t.Fatal("windows 应存在")
	}
	if payload["min_version"] != "1.3.18" || payload["too_low"] != true {
		t.Fatalf("min_version/too_low 不符：%v", payload)
	}
	if payload["latest"] != "1.3.18" || payload["available"] != true {
		t.Fatalf("latest/available 不符：%v", payload)
	}
	if CheckRelease(m, "nope", "1.0.0") != nil {
		t.Fatal("未知平台应返回 nil")
	}
}

func TestParseSince(t *testing.T) {
	valid := []string{"2026-05-06", "2026-05-06 12:00:00", "2026-05-06T12:00:00.123456Z", "2026-05-06 12:00:00+08:00"}
	for _, v := range valid {
		if ParseSince(v) != v {
			t.Errorf("%q 应接受", v)
		}
	}
	for _, v := range []string{"", "not-a-time", "2026-13-40 99:99:99", "2026-05-06; drop table users"} {
		if ParseSince(v) != "" {
			t.Errorf("%q 应忽略", v)
		}
	}
}
