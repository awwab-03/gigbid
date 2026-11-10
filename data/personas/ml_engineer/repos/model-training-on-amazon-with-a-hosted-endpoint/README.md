# model-training-on-amazon-with-a-hosted-endpoint

Model training on Amazon with a hosted endpoint - managed training jobs and a real-time endpoint behind their API gateway.

## Stack
- AWS SageMaker
- scikit-learn
- Model evaluation

## Quickstart
```
git clone <repo>
make install && make run
```

## Notes
Built for CareBridge Clinics (synthetic) in 2024. Outcome: no-show prediction AUC 0.84; reminder calls targeted to the riskiest 20% of bookings.
