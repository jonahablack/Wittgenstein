# Deployment Guide

This guide covers deploying the Wittgenstein project to Vercel (frontend) and Render (backend).

## Architecture

- **Frontend**: React app deployed on Vercel
- **Backend**: Flask API deployed on Render
- **Communication**: Frontend calls backend API via environment variables

## Prerequisites

1. GitHub repository with your code
2. Vercel account (free)
3. Render account (free)
4. OpenAI API key

## Frontend Deployment (Vercel)

### 1. Connect Repository to Vercel

1. Go to [vercel.com](https://vercel.com)
2. Click "New Project"
3. Import your GitHub repository
4. Set the **Root Directory** to `client`
5. Set **Build Command** to `npm run vercel-build`
6. Set **Output Directory** to `dist`

### 2. Configure Environment Variables

In Vercel dashboard, go to Settings → Environment Variables:

```
REACT_APP_API_URL=https://your-backend-url.onrender.com
```

### 3. Deploy

Click "Deploy" - Vercel will automatically build and deploy your frontend.

## Backend Deployment (Render)

### 1. Create New Web Service

1. Go to [render.com](https://render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `wittgenstein-backend`
   - **Root Directory**: `server`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `./start.sh`

### 2. Configure Environment Variables

In Render dashboard, go to Environment:

```
OPENAI_API_KEY=your_actual_openai_api_key
FLASK_ENV=production
PORT=3000
```

### 3. Deploy

Click "Create Web Service" - Render will build and deploy your backend.

## Post-Deployment Configuration

### 1. Update Frontend API URL

After backend deployment, update the frontend environment variable:

1. Go to Vercel dashboard
2. Settings → Environment Variables
3. Update `REACT_APP_API_URL` with your actual Render URL
4. Redeploy the frontend

### 2. Test the Deployment

1. Visit your Vercel frontend URL
2. Upload a test PDF
3. Try formalizing it
4. Check that the backend processes the request

## Environment Variables Reference

### Frontend (Vercel)
- `REACT_APP_API_URL`: Backend API URL (e.g., `https://wittgenstein-backend.onrender.com`)

### Backend (Render)
- `OPENAI_API_KEY`: Your OpenAI API key
- `FLASK_ENV`: Set to `production`
- `PORT`: Render sets this automatically

## Troubleshooting

### Common Issues

1. **CORS Errors**: Make sure `Flask-CORS` is installed and configured
2. **API Key Issues**: Verify your OpenAI API key is set correctly
3. **Build Failures**: Check the build logs in Vercel/Render dashboards
4. **File Upload Issues**: Ensure upload directories exist and have proper permissions

### Debugging

1. Check Render logs for backend issues
2. Check Vercel function logs for frontend issues
3. Use browser dev tools to inspect network requests
4. Verify environment variables are set correctly

## Cost Considerations

- **Vercel**: Free tier includes 100GB bandwidth/month
- **Render**: Free tier includes 750 hours/month (enough for most use cases)
- **OpenAI API**: Pay per use based on token consumption

## Security Notes

- Never commit API keys to your repository
- Use environment variables for all sensitive data
- The `.gitignore` file excludes `api_call.py` to prevent accidental commits
- Consider using Render's database for storing API keys securely

## Scaling

For higher traffic:
- Upgrade Render plan for more resources
- Consider using a CDN for file uploads
- Implement caching for frequently accessed data
- Monitor API usage and costs
