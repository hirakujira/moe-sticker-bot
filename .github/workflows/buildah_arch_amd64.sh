
GITHUB_TOKEN=$1

buildah login -u star-39 -p $GITHUB_TOKEN ghcr.io

#################################
if false ; then

c1=$(buildah from docker://archlinux:latest)

buildah run $c1 -- pacman -Sy
buildah run $c1 -- pacman --noconfirm -S libheif ffmpeg imagemagick curl libarchive python python-pip
buildah run $c1 -- sh -c 'yes | pacman -Scc'

buildah run $c1 -- pip3 install lottie[GIF] cairosvg
 
buildah config --cmd '/moe-sticker-bot' $c1

buildah commit $c1 moe-sticker-bot:base

buildah push moe-sticker-bot:base ghcr.io/star-39/moe-sticker-bot:base

fi
#################################

c1=$(buildah from ghcr.io/star-39/moe-sticker-bot:base)

# Build MSB go bin
go version
go build -o moe-sticker-bot cmd/main.go 
buildah copy $c1 moe-sticker-bot /moe-sticker-bot

# Build react app
cd web/webapp3/
npm install
PUBLIC_URL=/webapp/edit npm run build
buildah copy $c1 build/ /webapp

buildah commit $c1 moe-sticker-bot:latest

buildah push moe-sticker-bot ghcr.io/star-39/moe-sticker-bot:amd64
buildah push moe-sticker-bot ghcr.io/star-39/moe-sticker-bot:latest
