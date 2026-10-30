# Complete-source private candidate. Do not publish/build publicly before rights approval.
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 judge && useradd --uid 10001 --gid 10001 --no-create-home judge && mkdir /var/lib/se6-competition && chown judge:judge /var/lib/se6-competition
COPY hosted_judge /app/hosted_judge
COPY tools /app/tools
COPY benchmark /app/benchmark
COPY dynamic /app/dynamic
COPY canonical /app/canonical
COPY private-native /app/private-native
COPY awareness_native /app/awareness_native
COPY evidence /app/evidence
COPY native-manifest.json public-review.json frozen-replays.json current-operator-coverage.json candidate-field-controls.json COMPLETE_SOURCE_MANIFEST_PRIVATE.json /app/
COPY heldout /app/heldout
ENV SE6_PAIR_STORE=/var/lib/se6-competition
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "-B", "tools/run_dashboard.py", "--hosted", "--port", "8080"]
