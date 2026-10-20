//go:build !android

package mobile

func UpdateNetwork(raw string) error { return nil }

type NetworkBinder interface{ BindSocket(fd int64) error }

func SetNetworkBinder(b NetworkBinder) {}
