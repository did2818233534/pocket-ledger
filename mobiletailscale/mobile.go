// Package mobile embeds the upstream Tailscale userspace client for ledger-only traffic.
package mobile

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/netip"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"tailscale.com/tsnet"
)

var mu sync.Mutex
var server *tsnet.Server

func Start(directory string) error {
	mu.Lock()
	defer mu.Unlock()
	if server != nil {
		return nil
	}
	if err := os.MkdirAll(directory, 0700); err != nil {
		return err
	}
	// Android apps have neither a home directory nor a writable system temp directory.
	// ipnlocal also uses logpolicy independently of Server.Dir.
	if err := os.Setenv("TS_LOGS_DIR", directory); err != nil {
		return err
	}
	if err := os.Setenv("TMPDIR", directory); err != nil {
		return err
	}
	s := &tsnet.Server{Dir: directory, Hostname: "pocket-ledger", Logf: func(string, ...any) {}, UserLogf: func(string, ...any) {}}
	if err := s.Start(); err != nil {
		return err
	}
	server = s
	return nil
}

func current() (*tsnet.Server, error) {
	mu.Lock()
	defer mu.Unlock()
	if server == nil {
		return nil, errors.New("Tailscale 未开启")
	}
	return server, nil
}

func Login() error {
	s, err := current()
	if err != nil {
		return err
	}
	lc, err := s.LocalClient()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return lc.StartLoginInteractive(ctx)
}

// Stop leaves the node identity on disk so enabling it again does not require a new login.
func Stop() error {
	mu.Lock()
	defer mu.Unlock()
	if server == nil {
		return nil
	}
	s := server
	server = nil
	return s.Close()
}

func Logout() error {
	s, err := current()
	if err != nil {
		return err
	}
	lc, err := s.LocalClient()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err = lc.Logout(ctx); err != nil {
		return err
	}
	return Stop()
}

type peer struct {
	Name    string `json:"name"`
	IP      string `json:"ip"`
	Online  bool   `json:"online"`
	Expired bool   `json:"expired"`
}

func Status() (string, error) {
	s, err := current()
	if err != nil {
		return "", err
	}
	lc, err := s.LocalClient()
	if err != nil {
		return "", err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	st, err := lc.Status(ctx)
	if err != nil {
		return "", err
	}
	peers := []peer{}
	for _, p := range st.Peer {
		for _, ip := range p.TailscaleIPs {
			if ip.Is4() {
				peers = append(peers, peer{p.HostName, ip.String(), p.Online, p.Expired})
				break
			}
		}
	}
	sort.Slice(peers, func(i, j int) bool { return peers[i].Name < peers[j].Name })
	b, err := json.Marshal(map[string]any{"state": st.BackendState, "authURL": st.AuthURL, "peers": peers, "health": st.Health})
	return string(b), err
}

func validHost(host string) bool {
	ip, err := netip.ParseAddr(host)
	return err == nil && netip.MustParsePrefix("100.64.0.0/10").Contains(ip)
}

// Exchange can only contact the ledger port on a Tailscale IPv4 node. No proxy is exposed.
func Exchange(host, body, timestamp, signature string) (string, error) {
	return exchange(host, body, timestamp, signature, "/sync")
}

// Probe proves the server knows the pairing key before any ledger data is sent.
func Probe(host, body, timestamp, signature string) (string, error) {
	return exchange(host, body, timestamp, signature, "/identity")
}

func exchange(host, body, timestamp, signature, path string) (string, error) {
	if !validHost(host) {
		return "", errors.New("请选择 Tailscale 网络中的电脑")
	}
	if len(body) > 4*1024*1024 {
		return "", errors.New("账本超过单次同步大小限制")
	}
	s, err := current()
	if err != nil {
		return "", err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 18*time.Second)
	defer cancel()
	tr := &http.Transport{DialContext: s.Dial, DisableKeepAlives: true}
	defer tr.CloseIdleConnections()
	client := &http.Client{Transport: tr, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	req, err := http.NewRequestWithContext(ctx, "POST", "http://"+net.JoinHostPort(host, "47831")+path, strings.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Time", timestamp)
	req.Header.Set("X-Signature", signature)
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 4097))
	if err != nil {
		return "", err
	}
	if len(data) > 4096 {
		return "", errors.New("电脑响应过大")
	}
	b, err := json.Marshal(map[string]any{"code": resp.StatusCode, "body": string(data), "signature": resp.Header.Get("X-Signature")})
	return string(b), err
}
