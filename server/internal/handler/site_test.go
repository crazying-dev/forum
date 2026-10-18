package handler

import "testing"

func TestParseSiteAnnouncement(t *testing.T) {
	got := parseSiteAnnouncement([]byte(`{"enabled":true,"text":"站点公告","version":3,"updated_at":"2026-10-18T08:00:00+08:00"}`))
	want := SiteAnnouncement{Enabled: true, Text: "站点公告", Version: 3, UpdatedAt: "2026-10-18T08:00:00+08:00"}
	if got != want {
		t.Fatalf("got %+v, want %+v", got, want)
	}

	if def := parseSiteAnnouncement([]byte(`not-json`)); def.Enabled || def.Text != "" || def.Version != 0 || def.UpdatedAt != "" {
		t.Fatalf("invalid json should fall back to default: %+v", def)
	}
	if def := parseSiteAnnouncement(nil); def.Enabled || def.Version != 0 {
		t.Fatalf("nil should fall back to default: %+v", def)
	}
}
