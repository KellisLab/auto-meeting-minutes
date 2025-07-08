import google.generativeai as genai

genai.configure(api_key="AIzaSyDNxuBS5JcP5zNOiJIRBCJsz_T8YP22584")
models = genai.list_models()
for model in models:
    print(model.name)
