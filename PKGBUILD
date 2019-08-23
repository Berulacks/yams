# Maintainer: Derin Yarsuvat <derin.aur at fea dot st>
pkgname=python-yams-git
pkgrel=1
pkgver=0.7.r3.gf0a8377
pkgdesc="A Last.FM scrobbler for MPD"
arch=('x86_64')
url="https://github.com/Berulacks/yams"
license=('GPL3')
depends=('python' 'mpd' 'python-pyaml' 'python-mpd2' 'python-requests' 'python-psutil')
makedepends=('python-setuptools')
source=("${pkgname}::git://github.com/Berulacks/yams.git")
sha256sums=('SKIP')
pkgver() {
  cd "$pkgname"
  git describe --long --tags | sed 's/\([^-]*-g\)/r\1/;s/-/./g;s/^v//'
}

build() {
	cd "$srcdir/$pkgname"
	python setup.py build
}

package() {
	cd "$srcdir/$pkgname"
	python setup.py install --root="$pkgdir/" --optimize=1 --skip-build
	install -D "yams.service" "$pkgdir/usr/lib/systemd/user/yams.service"
}
