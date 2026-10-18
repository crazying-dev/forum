package database

import "testing"

func TestNormalizeEmail(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"  Foo.Bar+Spam@Example.COM ", "foo.bar@example.com"},
		{"user@example.com", "user@example.com"},
		{"user+tag@example.com", "user@example.com"},
		{"user+tag+more@example.com", "user@example.com"},
		{"no-at-sign", "no-at-sign"},
		{"", ""},
	}
	for _, tc := range cases {
		if got := NormalizeEmail(tc.in); got != tc.want {
			t.Errorf("NormalizeEmail(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestMatchEmailBlacklist(t *testing.T) {
	cases := []struct {
		name     string
		email    string
		patterns []string
		want     bool
	}{
		{"exact hit", "user@example.com", []string{"user@example.com"}, true},
		{"exact hit case-insensitive", "User@Example.COM", []string{"USER@example.com"}, true},
		{"exact hit ignores +tag", "user+spam@example.com", []string{"user@example.com"}, true},
		{"exact miss other local", "other@example.com", []string{"user@example.com"}, false},
		{"exact miss other domain", "user@other.com", []string{"user@example.com"}, false},
		{"domain hit", "any@example.com", []string{"@example.com"}, true},
		{"domain hit with tag", "any+tag@example.com", []string{"@example.com"}, true},
		{"domain hit case-insensitive", "any@Example.COM", []string{"@EXAMPLE.com"}, true},
		{"domain wildcard hit", "any@example.com", []string{"*@example.com"}, true},
		{"domain wildcard hit with tag", "any+tag@example.com", []string{"*@example.com"}, true},
		{"domain wildcard case-insensitive", "any@Example.COM", []string{"*@EXAMPLE.COM"}, true},
		{"domain does not match subdomain", "any@sub.example.com", []string{"@example.com"}, false},
		{"wildcard does not match subdomain", "any@sub.example.com", []string{"*@example.com"}, false},
		{"other domain miss", "any@other.com", []string{"@example.com", "*@example.org"}, false},
		{"empty patterns", "any@example.com", nil, false},
		{"blank pattern skipped", "any@example.com", []string{"  ", ""}, false},
		{"invalid email", "not-an-email", []string{"@example.com", "*@example.com"}, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := MatchEmailBlacklist(tc.email, tc.patterns); got != tc.want {
				t.Errorf("MatchEmailBlacklist(%q, %v) = %v, want %v", tc.email, tc.patterns, got, tc.want)
			}
		})
	}
}
