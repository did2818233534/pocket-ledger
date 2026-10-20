package mobile

import "testing"

func TestRemoteDestination(t *testing.T) {
	for _, host := range []string{"100.64.0.1", "100.77.91.15", "100.127.255.254"} {
		if !validHost(host) {
			t.Errorf("rejected tailnet %s", host)
		}
	}
	for _, host := range []string{"192.168.1.1", "127.0.0.1", "8.8.8.8", "100.63.255.255", "100.128.0.1", "login.tailscale.com", "100.77.91.15:80", "100.77.91.15/x"} {
		if validHost(host) {
			t.Errorf("accepted non-tailnet %s", host)
		}
		if _, err := Exchange(host, "{}", "1", "x"); err == nil {
			t.Errorf("Exchange accepted %s", host)
		}
	}
}
