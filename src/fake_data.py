


from werkzeug.security import generate_password_hash, check_password_hash

from werkzeug.security import generate_password_hash

sample_users = [
    {
        "username": "Isabella Rossi",
        "email": "isabella@rossi.com",
        "password": generate_password_hash("password"),
        "university": "Columbia",
        "user_type": "Student",
        "grad": "2025",
        "major": "Computer Science",
        "Interests": ["open source", "robotics", "biotech", "computer vision"],
        "skills": ["Python", "Machine Learning", "CAD", "Data Analysis"],
        "biography": "Isabella is passionate about blending robotics with biotechnology to create innovative solutions. Her work often involves complex machine learning models to improve data accuracy in various biotechnological applications.",
        "personal_website": "example.com",
        "orgs": ["Robotics Club", "Biotech Society", "Data Science Club"],
        "links" : [],
        "github_link": "github.com",
        "upvotes": [],
        "portfolio": [
            {
                "projectName": "Robotic Arm for Surgery",
                "projectDescription": "This project involves developing a robotic arm equipped with advanced sensors and actuators for assisting surgeons in precision tasks. The system integrates machine learning algorithms to predict and assist in surgical procedures, enhancing the efficiency and safety of operations.",
                "createdBy": "Isabella Rossi",
                "upvotes": [],
                "tags": ["robotics", "machine learning", "biotech"],
                "layers": [],
                "links": [],
                "created_at": "2024-06-01"
            },
            {
                "projectName": "Biotech Data Analyzer",
                "projectDescription": "The Biotech Data Analyzer project focuses on creating software that processes and analyzes large sets of biotechnological data. It uses machine learning techniques to identify patterns and generate insights that can be used for research and development in biotech industries.",
                "createdBy": "Isabella Rossi",
                "upvotes": [],
                "tags": ["biotech", "data analysis", "machine learning"],
                "layers": [],
                "links": [],
                "created_at": "2024-05-15"
            },
            {
                "projectName": "Autonomous Drone for Agriculture",
                "projectDescription": "This project involves the design and development of an autonomous drone system for monitoring and managing agricultural fields. The drone uses computer vision and machine learning to assess crop health, identify pest infestations, and optimize farming practices.",
                "createdBy": "Isabella Rossi",
                "upvotes": [],
                "tags": ["drone", "computer vision", "agriculture"],
                "layers": [],
                "links": [],
                "created_at": "2024-04-20"
            }
        ],
        "comments": [],
        "links": ["linkedin.com/in/isabellarossi", "github.com/isabellarossi"],
        "resume": ""
    },
    {
        "username": "Dimitri Ivanov",
        "email": "dimitri@ivanov.com",
        "password": generate_password_hash("password"),
        "university": "Columbia",
        "user_type": "Student",
        "grad": "2025",
        "major": "Computer Science",
        "Interests": ["distributed systems", "open source", "web development", "aeronautics"],
        "skills": ["JavaScript", "React", "Node.js", "System Design"],
        "biography": "Dimitri has a strong interest in developing scalable web applications and distributed systems. His projects often focus on creating robust software solutions that can handle high traffic and complex workflows.",
        "personal_website": "example.com",
        "orgs": ["Web Dev Club", "Open Source Initiative", "Aerospace Society"],
        "upvotes": [],
        "portfolio": [
            {
                "projectName": "Scalable Web Application",
                "projectDescription": "This project involves creating a highly scalable web application using modern web technologies. The application is designed to handle millions of users simultaneously, providing a seamless and efficient user experience.",
                "createdBy": "Dimitri Ivanov",
                "upvotes": [],
                "tags": ["web development", "scalability", "system design"],
                "layers": [],
                "links": [],
                "created_at": "2024-05-10"
            },
            {
                "projectName": "Open Source Distributed System",
                "projectDescription": "An open source project focused on building a distributed system for efficient data processing. The system utilizes a microservices architecture to ensure reliability and performance, making it suitable for a variety of applications.",
                "createdBy": "Dimitri Ivanov",
                "upvotes": [],
                "tags": ["distributed systems", "open source", "microservices"],
                "layers": [],
                "links": [],
                "created_at": "2024-04-25"
            },
            {
                "projectName": "Aeronautics Simulation Software",
                "projectDescription": "This project entails developing a simulation software for aeronautics applications. The software models various flight scenarios and provides tools for analyzing and optimizing aircraft performance.",
                "createdBy": "Dimitri Ivanov",
                "upvotes": [],
                "tags": ["aeronautics", "simulation", "software development"],
                "layers": [],
                "links": [],
                "created_at": "2024-03-30"
            }
        ],
        "comments": [],
        "links": ["linkedin.com/in/dimitriivanov", "github.com/dimitriivanov"],
        "resume": ""
    },
    {
        "username": "Aisha Patel",
        "email": "aisha@patel.com",
        "password": generate_password_hash("password"),
        "university": "Columbia",
        "user_type": "Student",
        "grad": "2025",
        "major": "Computer Science",
        "Interests": ["machine learning", "computer vision", "robotics", "autonomous systems"],
        "skills": ["Python", "TensorFlow", "ROS", "Data Analysis"],
        "biography": "Aisha is an enthusiast of integrating machine learning with robotics to develop autonomous systems. Her projects often revolve around using computer vision to enhance the functionality and efficiency of robots in various tasks.",
        "personal_website": "example.com",
        "orgs": ["AI Club", "Robotics Society", "Women in Tech"],
        "links" : [],
        "github_link": "github.com",
        "upvotes": [],
        "portfolio": [
            {
                "projectName": "Autonomous Navigation System",
                "projectDescription": "This project focuses on developing an autonomous navigation system for robots using computer vision and machine learning. The system is designed to enable robots to navigate complex environments without human intervention.",
                "createdBy": "Aisha Patel",
                "upvotes": [],
                "tags": ["autonomous systems", "computer vision", "machine learning"],
                "layers": [],
                "links": [],
                "created_at": "2024-06-01"
            },
            {
                "projectName": "Machine Learning for Precision Agriculture",
                "projectDescription": "The project involves using machine learning algorithms to analyze agricultural data and provide insights for precision farming. This helps in optimizing crop yields and managing resources efficiently.",
                "createdBy": "Aisha Patel",
                "upvotes": [],
                "tags": ["machine learning", "agriculture", "data analysis"],
                "layers": [],
                "links": [],
                "created_at": "2024-05-15"
            },
            {
                "projectName": "Robot Vision for Object Detection",
                "projectDescription": "This project aims to develop an advanced robot vision system capable of detecting and recognizing objects in real-time. The system uses deep learning techniques to improve accuracy and efficiency in various robotic applications.",
                "createdBy": "Aisha Patel",
                "upvotes": [],
                "tags": ["robotics", "computer vision", "deep learning"],
                "layers": [],
                "links": [],
                "created_at": "2024-04-20"
            }
        ],
        "comments": [],
        "links": ["linkedin.com/in/aishapatel", "github.com/aishapatel"],
        "resume": ""
    },
    {
        "username": "Li Wei",
        "email": "li@wei.com",
        "password": generate_password_hash("password"),
        "university": "Columbia",
        "user_type": "Student",
        "grad": "2025",
        "major": "Computer Science",
        "Interests": ["aeronautics", "robotics", "control systems", "AI"],
        "skills": ["C++", "Matlab", "Simulink", "Control Theory"],
        "biography": "Li is fascinated by the intersection of aeronautics and robotics. His work focuses on developing advanced control systems for aerial vehicles, incorporating AI to enhance flight stability and efficiency.",
        "personal_website": "example.com",
        "orgs": ["Aerospace Club", "Robotics Team", "AI Research Group"],
        "links" : [],
        "github_link": "github.com",
        "upvotes": [],
        "portfolio": [
            {
                "projectName": "Advanced Flight Control System",
                "projectDescription": "This project involves designing an advanced flight control system for drones. The system uses AI algorithms to enhance flight stability and optimize performance under various conditions.",
                "createdBy": "Li Wei",
                "upvotes": [],
                "tags": ["aeronautics", "control systems", "AI"],
                "layers": [],
                "links": [],
                "created_at": "2024-05-10"
            },
            {
                "projectName": "Robotic Arm for Space Missions",
                "projectDescription": "The project aims to develop a robotic arm designed for space missions. The arm is equipped with advanced control systems and AI to perform tasks autonomously in the challenging environment of space.",
                "createdBy": "Li Wei",
                "upvotes": [],
                "tags": ["space robotics", "control systems", "AI"],
                "layers": [],
                "links": [],
                "created_at": "2024-04-25"
            },
            {
                "projectName": "AI-Powered Aerodynamic Analysis",
                "projectDescription": "This project focuses on developing AI-powered tools for aerodynamic analysis. These tools are designed to optimize the design and performance of aerial vehicles through advanced simulations and data analysis.",
                "createdBy": "Li Wei",
                "upvotes": [],
                "tags": ["aeronautics", "AI", "data analysis"],
                "layers": [],
                "links": [],
                "created_at": "2024-03-30"
            }
        ],
        "comments": [],
        "links": ["linkedin.com/in/liwei", "github.com/liwei"],
        "resume": ""
    }
]
