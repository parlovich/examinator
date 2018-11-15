node {
    properties([
            parameters([
                    string(name: 'USER_ID', description: 'the student name'),
                    string(name: 'TASK', description: 'name of the task the student is trying to implement'),
                    string(name: 'REPO_URL', description: 'git repo with the student\'s implementation'),
                    string(name: 'TEST_REPO_URL', description: 'git repo with the tests to the task')
            ])
    ])

    // Directory to where to clone the student's sources
    def sources_dir = "implementation"
    // Directory to where to clone unittests for the task
    def tests_dir = "tests"

    stage('Preparation') {
        currentBuild.displayName = "#${env.BUILD_NUMBER} ${TASK} ${USER_ID}"

        env.JAVA_HOME = "${tool 'jdk8'}"
        env.PATH = "${env.JAVA_HOME}/bin:${env.PATH}"

        cleanWs()
    }
    stage('Checkout') {
        // Git clone the student's sources to ${sources_dir} directory
        checkout([$class           : 'GitSCM',
                  branches         : [[name: '*/master']],
                  userRemoteConfigs: [[url: '$REPO_URL']],
                  extensions       : [
                          [$class: 'CloneOption', noTags: true, reference: '', shallow: true],
                          [$class: 'RelativeTargetDirectory', relativeTargetDir: "${sources_dir}"]
                  ]
        ])
        // Git clone unittests for the task to ${tests_dir} directory
        checkout([$class           : 'GitSCM',
                  branches         : [[name: '*/master']],
                  userRemoteConfigs: [[url: '$TEST_REPO_URL']],
                  extensions       : [
                          [$class: 'CloneOption', noTags: true, reference: '', shallow: true],
                          [$class: 'RelativeTargetDirectory', relativeTargetDir: "${tests_dir}"]
                  ]
        ])
    }
    stage('Test') {
        withMaven(
                maven: 'M3',
                jdk: 'jdk8',
                // Create maven local repository
                mavenLocalRepo: '.repository'
        ) {
            // Build artifacts from the student sources.
            // The artifact will be published to the local maven repository
            dir("${sources_dir}") {
                sh "mvn clean -DskipTests install"
            }
            // Run tests. The student's artifact will be gotten from maven local repository as dependency
            dir("${tests_dir}") {
                sh 'mvn clean test'
                junit '**/target/surefire-reports/TEST-*.xml'
            }
        }
    }
}