 #!/bin/bash

docker system prune -f
docker compose build --no-cache
docker push osvasldas97/kainos-scraper
