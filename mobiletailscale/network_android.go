package mobile

import (
	"encoding/json"
	"net"
	"sync"
	"tailscale.com/net/netmon"
	"tailscale.com/net/netns"
)

var interfaceMu sync.Mutex
var interfaces []netmon.Interface

func init() {
	netmon.RegisterInterfaceGetter(func() ([]netmon.Interface, error) {
		interfaceMu.Lock()
		defer interfaceMu.Unlock()
		return append([]netmon.Interface(nil), interfaces...), nil
	})
}

// UpdateNetwork supplies Android's permitted ConnectivityManager view instead of /proc/net.
func UpdateNetwork(raw string) error {
	var data struct {
		Default    string `json:"default"`
		Interfaces []struct {
			Name      string   `json:"name"`
			MTU       int      `json:"mtu"`
			Addresses []string `json:"addresses"`
		} `json:"interfaces"`
	}
	if err := json.Unmarshal([]byte(raw), &data); err != nil {
		return err
	}
	list := []netmon.Interface{}
	for i, v := range data.Interfaces {
		addrs := []net.Addr{}
		for _, a := range v.Addresses {
			ip, n, err := net.ParseCIDR(a)
			if err == nil {
				n.IP = ip
				addrs = append(addrs, n)
			}
		}
		mtu := v.MTU
		if mtu <= 0 {
			mtu = 1500
		}
		list = append(list, netmon.Interface{Interface: &net.Interface{Index: i + 1, Name: v.Name, MTU: mtu, Flags: net.FlagUp | net.FlagRunning | net.FlagMulticast}, AltAddrs: addrs})
	}
	interfaceMu.Lock()
	interfaces = list
	interfaceMu.Unlock()
	netmon.UpdateLastKnownDefaultRouteInterface(data.Default)
	mu.Lock()
	defer mu.Unlock()
	if server != nil {
		server.Sys().NetMon.Get().InjectEvent()
	}
	return nil
}

// NetworkBinder connects Go sockets to the same Android network used by Java DNS.
type NetworkBinder interface{ BindSocket(fd int64) error }

func SetNetworkBinder(b NetworkBinder) {
	netns.SetAndroidBindToNetworkFunc(func(fd int) error { return b.BindSocket(int64(fd)) })
}
